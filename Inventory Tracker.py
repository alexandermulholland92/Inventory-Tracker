import datetime
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Inventory Tracker", page_icon="📦", layout="centered")

class InventoryTracker:
    def __init__(self):
        # Renamed key from 'items' to 'inventory' to prevent collision with st.session_state.items()
        if "inventory" not in st.session_state:
            st.session_state.inventory = {}

    def add_item(self, item_name, category, initial_qty=0, notes=""):
        """Registers an item with a starting baseline."""
        st.session_state.inventory[item_name] = {
            "Category": category,
            "Qty": initial_qty,
            "Updated By": "System Setup",
            "Date": datetime.date.today().isoformat(),
            "Notes": notes
        }

    def record_movement(self, item_name, amount, updated_by):
        """Tracks ins (positive) and outs (negative) while forcing accountability."""
        if item_name in st.session_state.inventory:
            st.session_state.inventory[item_name]["Qty"] += amount
            st.session_state.inventory[item_name]["Updated By"] = updated_by
            st.session_state.inventory[item_name]["Date"] = datetime.date.today().isoformat()
            
            direction = "added" if amount > 0 else "removed"
            st.toast(f"[{item_name}] {direction} {abs(amount)}. New Total: {st.session_state.inventory[item_name]['Qty']} (Logged by {updated_by})")
        else:
            st.error(f"Error: {item_name} does not exist. Add it first.")

    def show_inventory(self):
        """Displays the current ledger on the Streamlit web screen."""
        if not st.session_state.inventory:
            st.info("No items in inventory.")
            return

        df = pd.DataFrame.from_dict(st.session_state.inventory, orient='index')
        st.dataframe(df, use_container_width=True)

# --- App Layout & Execution ---

st.title("📦 Inventory Tracker")

tracker = InventoryTracker()

# Populate initial inventory if empty
if "initialized" not in st.session_state:
    tracker.add_item("2.1 Units", "Hardware", 20)
    tracker.record_movement("2.1 Units", -3, "Harrison")
    tracker.record_movement("2.1 Units", 5, "Malavika")
    st.session_state.initialized = True

# Display inventory table
tracker.show_inventory()
