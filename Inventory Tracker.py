import datetime
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Inventory Tracker", page_icon="📦", layout="centered")

class InventoryTracker:
    def __init__(self):
        # Initialize dictionary for current stock levels
        if "inventory" not in st.session_state:
            st.session_state.inventory = {}
        # Initialize list for the historical movement log
        if "movement_log" not in st.session_state:
            st.session_state.movement_log = []

    def log_action(self, item_name, action, amount, updated_by, notes=""):
        """Helper function to record transactions in the history log."""
        log_entry = {
            "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Item Name": item_name,
            "Action": action,
            "Qty Changed": amount,
            "Updated By": updated_by,
            "Notes": notes
        }
        st.session_state.movement_log.insert(0, log_entry) # Insert at top (newest first)

    def add_item(self, item_name, category, initial_qty, updated_by, notes=""):
        """Registers a new item with a starting baseline."""
        if item_name in st.session_state.inventory:
            st.error(f"Item '{item_name}' already exists in the inventory.")
            return False

        st.session_state.inventory[item_name] = {
            "Category": category,
            "Qty": initial_qty,
            "Updated By": updated_by,
            "Date": datetime.date.today().isoformat(),
            "Notes": notes
        }
        self.log_action(item_name, "Registered", initial_qty, updated_by, notes)
        st.toast(f"✅ '{item_name}' added to inventory!")
        return True

    def record_movement(self, item_name, amount, updated_by, notes=""):
        """Tracks ins (positive) and outs (negative)."""
        if item_name in st.session_state.inventory:
            st.session_state.inventory[item_name]["Qty"] += amount
            st.session_state.inventory[item_name]["Updated By"] = updated_by
            st.session_state.inventory[item_name]["Date"] = datetime.date.today().isoformat()
            
            direction = "Checked In" if amount > 0 else "Checked Out"
            self.log_action(item_name, direction, amount, updated_by, notes)
            st.toast(f"🔄 [{item_name}] {direction} {abs(amount)}. New Total: {st.session_state.inventory[item_name]['Qty']}")
            return True
        else:
            st.error(f"Error: {item_name} does not exist.")
            return False

    def delete_item(self, item_name, updated_by):
        """Completely removes an item from the inventory tracker."""
        if item_name in st.session_state.inventory:
            del st.session_state.inventory[item_name]
            self.log_action(item_name, "Deleted completely", 0, updated_by, "Item removed from system")
            st.toast(f"🗑️ '{item_name}' permanently deleted!")
            return True
        else:
            st.error(f"Error: {item_name} could not be found.")
            return False

    def clear_history(self):
        """Empties the entire transaction log."""
        st.session_state.movement_log = []
        st.toast("🧹 Transaction history cleared!")
        return True

    def show_inventory(self):
        """Displays the current ledger."""
        if not st.session_state.inventory:
            st.info("No items in inventory. Go to the 'Register New Item' tab to get started.")
            return

        df = pd.DataFrame.from_dict(st.session_state.inventory, orient='index')
        st.dataframe(df, use_container_width=True)

    def show_log(self):
        """Displays the historical transaction log."""
        if not st.session_state.movement_log:
            st.info("No movements recorded yet.")
            return
            
        df_log = pd.DataFrame(st.session_state.movement_log)
        st.dataframe(df_log, use_container_width=True, hide_index=True)


# --- App Layout & Execution ---
st.title("📦 Inventory Tracker")

tracker = InventoryTracker()

# Create tabs for clean navigation
tab1, tab2, tab3 = st.tabs(["📋 Current Inventory", "➕ Register New Item", "📜 Transaction Log"])

# --- TAB 1: CURRENT INVENTORY & MOVEMENT ---
with tab1:
    st.subheader("Current Stock")
    tracker.show_inventory()
    
    if st.session_state.inventory:
        st.markdown("---")
        st.subheader("Process a Transaction")
        
        with st.form("movement_form"):
            item_list = list(st.session_state.inventory.keys())
            
            col1, col2 = st.columns(2)
            with col1:
                sel_item = st.selectbox("Select Item", item_list)
                action_type = st.radio("Action", ["📤 Check Out", "📥 Check In"], horizontal=True)
                mov_amount = st.number_input("Quantity", value=1, step=1, min_value=1)
            with col2:
                mov_user = st.text_input("Your Name", placeholder="e.g. Jane Doe")
                mov_notes = st.text_input("Reason / Notes (Optional)", placeholder="e.g. Job #1234")
                
            submit_movement = st.form_submit_button("Submit Transaction", type="primary")
            
            if submit_movement:
                if not mov_user.strip():
                    st.error("Please enter your name.")
                else:
                    # Convert to negative if Checking Out
                    final_amount = -mov_amount if "Check Out" in action_type else mov_amount
                    current_qty = st.session_state.inventory[sel_item]["Qty"]
                    
                    # Prevent checking out more than we have
                    if final_amount < 0 and abs(final_amount) > current_qty:
                        st.error(f"Cannot check out {abs(final_amount)}. There are only {current_qty} in stock.")
                    else:
                        if tracker.record_movement(sel_item, final_amount, mov_user, mov_notes):
                            st.rerun()

        # Danger Zone for Deleting Items
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("⚠️ Danger Zone: Delete Item"):
            st.warning("Deleting an item removes it permanently from the Current Stock. This action will be recorded in the Transaction Log.")
            with st.form("delete_form"):
                del_item = st.selectbox("Select Item to Delete", item_list)
                del_user = st.text_input("Authorized By (Your Name)", key="del_user_input", placeholder="e.g. Jane Doe")
                submit_delete = st.form_submit_button("Delete Item permanently")
                
                if submit_delete:
                    if not del_user.strip():
                        st.error("Please enter your name to authorize the deletion.")
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
                if tracker.add_item(new_item_name, new_category, new_qty, new_user, new_notes):
                    st.rerun()

# --- TAB 3: TRANSACTION LOG ---
with tab3:
    st.subheader("Movement History")
    tracker.show_log()
    
    # Danger Zone for Clearing History
    if st.session_state.movement_log:
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("⚠️ Danger Zone: Clear History"):
            st.warning("Are you sure? Clearing the history will permanently delete all records of past movements. This action cannot be undone.")
            if st.button("Clear All History", type="primary"):
                if tracker.clear_history():
                    st.rerun()
