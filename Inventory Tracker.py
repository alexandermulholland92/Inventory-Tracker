import datetime
from contextlib import contextmanager

import pandas as pd
import psycopg2
import psycopg2.extras
import streamlit as st
from psycopg2.pool import ThreadedConnectionPool

st.session_state.setdefault("sidebar_state", "collapsed")
st.set_page_config(page_title="Inventory Tracker", page_icon="📦", layout="centered",
                   initial_sidebar_state=st.session_state.sidebar_state)


# --- database connection ---------------------------------------------------
def db_url():
    """Read the Neon connection string out of Streamlit secrets."""
    try:
        return st.secrets["connections"]["rigs"]["url"]
    except Exception:
        st.error(
            "No database connection is configured.\n\n"
            "Open this app on share.streamlit.io, go to Settings -> Secrets, "
            "and add these two lines:\n\n"
            "[connections.rigs]\n"
            'url = "postgresql://...your Neon connection string..."'
        )
        st.stop()


@st.cache_resource
def pool():
    """One shared pool of connections for the whole app, opened lazily."""
    return ThreadedConnectionPool(1, 5, dsn=db_url(), connect_timeout=10)


def reset_pool():
    """Throw away the pool so the next call opens fresh connections."""
    try:
        pool().closeall()
    except Exception:
        pass
    pool.clear()


@contextmanager
def borrow():
    connections = pool()
    conn = connections.getconn()
    broken = False
    try:
        yield conn
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        broken = True
        raise
    except Exception:
        try:
            conn.rollback()
        except Exception:
            broken = True
        raise
    finally:
        try:
            connections.putconn(conn, close=broken)
        except Exception:
            pass


def run(work, retry=True):
    """Run `work(cursor)` inside a transaction, retrying once on a dead socket.

    Neon suspends the database after a few minutes of no traffic, which quietly
    kills any connection we were holding. The retry re-opens and tries again so
    the first person to touch the app after a quiet spell doesn't see an error.
    """
    try:
        with borrow() as conn:
            with conn.cursor() as cur:
                result = work(cur)
            conn.commit()
            return result
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        if not retry:
            raise
        reset_pool()
        return run(work, retry=False)


def db_op(query, params=(), fetch=None):
    """Run one statement. fetch: None, 'all' for rows, or 'df' for a DataFrame."""
    def work(cur):
        cur.execute(query, params)
        if fetch == "df":
            return pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
        if fetch == "all":
            return cur.fetchall()
        return None
    return run(work)


@st.cache_resource
def init_db():
    """Create the tables if they don't exist. Cached so it runs once, not every click."""
    db_op("CREATE TABLE IF NOT EXISTS inventory ("
          "item_name TEXT PRIMARY KEY, category TEXT, qty INTEGER NOT NULL DEFAULT 0, "
          "updated_by TEXT, date TEXT, notes TEXT)")
    db_op("CREATE TABLE IF NOT EXISTS movement_log (id SERIAL PRIMARY KEY, "
          '"timestamp" TEXT, item_name TEXT, action TEXT, qty_changed INTEGER, '
          "updated_by TEXT, notes TEXT)")
    return True


def flash(message):
    """Queue a toast for after the rerun, so it isn't wiped by the refresh."""
    st.session_state.flash_message = message


class InventoryTracker:
    def log_action(self, item_name, action, amount, updated_by, notes=""):
        """Records transactions in the history log."""
        db_op('INSERT INTO movement_log ("timestamp", item_name, action, qty_changed, '
              "updated_by, notes) VALUES (%s,%s,%s,%s,%s,%s)",
              (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               item_name, action, amount, updated_by, notes))

    def item_names(self):
        return [r[0] for r in db_op("SELECT item_name FROM inventory ORDER BY item_name",
                                    fetch="all")]

    def qty_of(self, item_name):
        rows = db_op("SELECT qty FROM inventory WHERE item_name = %s", (item_name,), fetch="all")
        return rows[0][0] if rows else None

    def add_item(self, item_name, category, initial_qty, updated_by, notes=""):
        """Registers a new item with a starting baseline."""
        rows = db_op("INSERT INTO inventory (item_name, category, qty, updated_by, date, notes) "
                     "VALUES (%s,%s,%s,%s,%s,%s) "
                     "ON CONFLICT (item_name) DO NOTHING RETURNING item_name",
                     (item_name, category, int(initial_qty), updated_by,
                      datetime.date.today().isoformat(), notes),
                     fetch="all")
        if not rows:
            st.error(f"Item '{item_name}' already exists in the inventory.")
            return False

        self.log_action(item_name, "Registered", int(initial_qty), updated_by, notes)
        flash(f"✅ '{item_name}' added to inventory!")
        return True

    def record_movement(self, item_name, amount, updated_by, notes=""):
        """Tracks ins (positive) and outs (negative).

        The stock check happens inside the UPDATE rather than in Python, so two
        people checking out the last unit at the same moment can't both succeed.
        """
        amount = int(amount)
        rows = db_op("UPDATE inventory SET qty = qty + %s, updated_by = %s, date = %s "
                     "WHERE item_name = %s AND qty + %s >= 0 RETURNING qty",
                     (amount, updated_by, datetime.date.today().isoformat(), item_name, amount),
                     fetch="all")
        if not rows:
            current = self.qty_of(item_name)
            if current is None:
                st.error(f"Error: {item_name} does not exist.")
            else:
                st.error(f"Cannot check out {abs(amount)}. Only {current} currently in stock.")
            return False

        new_qty = rows[0][0]
        direction = "Checked In" if amount > 0 else "Checked Out"
        self.log_action(item_name, direction, amount, updated_by, notes)
        flash(f"🔄 [{item_name}] {direction} {abs(amount)}. New Total: {new_qty}")
        return True

    def delete_item(self, item_name, updated_by):
        """Completely removes an item from the inventory tracker."""
        rows = db_op("DELETE FROM inventory WHERE item_name = %s RETURNING item_name",
                     (item_name,), fetch="all")
        if not rows:
            st.error(f"Error: {item_name} could not be found.")
            return False

        self.log_action(item_name, "Deleted completely", 0, updated_by, "Item removed from system")
        flash(f"🗑️ '{item_name}' permanently deleted!")
        return True

    def clear_history(self):
        """Empties the transaction log."""
        db_op("DELETE FROM movement_log")
        flash("🧹 Transaction history cleared!")
        return True

    def inventory_df(self):
        return db_op('SELECT item_name AS "Item Name", category AS "Category", qty AS "Qty", '
                     'updated_by AS "Updated By", date AS "Date", notes AS "Notes" '
                     "FROM inventory ORDER BY item_name", fetch="df")

    def log_df(self):
        return db_op('SELECT "timestamp" AS "Timestamp", item_name AS "Item Name", '
                     'action AS "Action", qty_changed AS "Qty Changed", '
                     'updated_by AS "Updated By", notes AS "Notes" '
                     "FROM movement_log ORDER BY id DESC", fetch="df")

    def show_inventory(self):
        """Displays current inventory."""
        df = self.inventory_df()
        if df.empty:
            st.info("No items registered yet. Use the **➕ Register New Item** tab above to add items.")
            return

        st.dataframe(df.set_index("Item Name"), use_container_width=True)

    def show_log(self):
        """Displays historical log."""
        df_log = self.log_df()
        if df_log.empty:
            st.info("No movements recorded yet.")
            return

        st.dataframe(df_log, use_container_width=True, hide_index=True)

    def has_log(self):
        return bool(db_op("SELECT 1 FROM movement_log LIMIT 1", fetch="all"))


# --- admin sidebar ---------------------------------------------------------
def admin_sidebar(tracker):
    """Render the password gate plus admin tools. Returns True when unlocked."""
    st.sidebar.header("System Access")
    password = st.secrets.get("ADMIN_PASSWORD", "")
    if not password:
        st.sidebar.warning("No ADMIN_PASSWORD is set in this app's Secrets, so the "
                           "delete and clear-history controls stay locked.")
        st.session_state.sidebar_state = "collapsed"
        return False

    is_admin = st.sidebar.text_input("Admin Key", type="password") == password
    st.session_state.sidebar_state = "expanded" if is_admin else "collapsed"
    if not is_admin:
        return False

    st.sidebar.divider()
    st.sidebar.subheader("Admin Controls")

    with st.sidebar.expander("Export CSV"):
        inventory = tracker.inventory_df()
        if inventory.empty:
            st.info("Inventory empty.")
        else:
            st.download_button("Download Inventory CSV",
                               inventory.to_csv(index=False).encode("utf-8"),
                               "inventory_export.csv", "text/csv")
        log = tracker.log_df()
        if log.empty:
            st.info("No transactions logged.")
        else:
            st.download_button("Download Transaction Log CSV",
                               log.to_csv(index=False).encode("utf-8"),
                               "movement_log.csv", "text/csv")
    return True


# --- App Layout & Execution ---
st.title("📦 Inventory Tracker")

init_db()
if "flash_message" in st.session_state:
    st.toast(st.session_state.pop("flash_message"))

tracker = InventoryTracker()
is_admin = admin_sidebar(tracker)

item_list_raw = tracker.item_names()
has_items = bool(item_list_raw)
item_list = item_list_raw if has_items else ["No items available"]

tab1, tab2, tab3 = st.tabs(["📋 Current Inventory & Check Out", "➕ Register New Item", "📜 Transaction Log"])

# --- TAB 1: CURRENT INVENTORY & MOVEMENT ---
with tab1:
    st.subheader("Current Stock")
    tracker.show_inventory()

    st.markdown("---")
    st.subheader("📤 Check Out / 📥 Check In Items")

    with st.form("movement_form"):
        col1, col2 = st.columns(2)
        with col1:
            sel_item = st.selectbox("Select Item", item_list, disabled=not has_items)
            action_type = st.radio("Action", ["📤 Check Out", "📥 Check In"], horizontal=True, disabled=not has_items)
            mov_amount = st.number_input("Quantity", value=1, step=1, min_value=1, disabled=not has_items)
        with col2:
            mov_user = st.text_input("Your Name", placeholder="e.g. Jane Doe", disabled=not has_items)
            mov_notes = st.text_input("Reason / Job # (Optional)", placeholder="e.g. Field Project A", disabled=not has_items)

        submit_movement = st.form_submit_button(
            "Submit Transaction" if has_items else "Add an item first to enable transactions",
            type="primary",
            disabled=not has_items
        )

        if submit_movement and has_items:
            if not mov_user.strip():
                st.error("Please enter your name.")
            else:
                final_amount = -mov_amount if "Check Out" in action_type else mov_amount
                if tracker.record_movement(sel_item, final_amount, mov_user, mov_notes):
                    st.rerun()

    # Danger Zone for Deleting Items - admin only
    if has_items and is_admin:
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("⚠️ Danger Zone: Delete Item"):
            st.warning("Deleting an item permanently removes it from Current Stock. This action will be logged in History.")
            with st.form("delete_form"):
                del_item = st.selectbox("Select Item to Delete", item_list)
                del_user = st.text_input("Authorized By (Your Name)", key="del_user_input", placeholder="e.g. Jane Doe")
                submit_delete = st.form_submit_button("Delete Item permanently")

                if submit_delete:
                    if not del_user.strip():
                        st.error("Please enter your name to authorize deletion.")
                    else:
                        if tracker.delete_item(del_item, del_user):
                            st.rerun()

# --- TAB 2: REGISTER NEW ITEM ---
with tab2:
    st.subheader("Add a New Item to Inventory")
    with st.form("new_item_form"):
        col1, col2 = st.columns(2)
        with col1:
            new_item_name = st.text_input("Item Name", placeholder="e.g. 2.1 Units")
            new_category = st.selectbox("Category", ["Hardware", "Tools", "Consumables", "Electronics", "Other"])
        with col2:
            new_qty = st.number_input("Starting Quantity", value=0, step=1, min_value=0)
            new_user = st.text_input("Logged By (Your Name)", placeholder="e.g. John Doe")

        new_notes = st.text_area("Notes / Description (Optional)")
        submit_new_item = st.form_submit_button("Register Item", type="primary")

        if submit_new_item:
            if not new_item_name.strip():
                st.error("Please enter an Item Name.")
            elif not new_user.strip():
                st.error("Please enter your name.")
            else:
                if tracker.add_item(new_item_name.strip(), new_category, new_qty, new_user, new_notes):
                    st.rerun()

# --- TAB 3: TRANSACTION LOG ---
with tab3:
    st.subheader("Movement History")
    tracker.show_log()

    # Danger Zone for Clearing History - admin only
    if is_admin and tracker.has_log():
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("⚠️ Danger Zone: Clear History"):
            st.warning("Permanently deletes all records of past movements. Cannot be undone.")
            if st.button("Clear All History", type="primary"):
                if tracker.clear_history():
                    st.rerun()
