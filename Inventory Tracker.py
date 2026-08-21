import datetime

class InventoryTracker:
    def __init__(self):
        self.items = {}

    def add_item(self, item_name, category, initial_qty=0, notes=""):
        """Registers an item with a starting baseline."""
        self.items[item_name] = {
            "Category": category,
            "Qty": initial_qty,
            "Updated By": "System Setup",
            "Date": datetime.date.today().isoformat(),
            "Notes": notes
        }

    def record_movement(self, item_name, amount, updated_by):
        """Tracks ins (positive) and outs (negative) while forcing accountability."""
        if item_name in self.items:
            self.items[item_name]["Qty"] += amount
            self.items[item_name]["Updated By"] = updated_by
            self.items[item_name]["Date"] = datetime.date.today().isoformat()
            
            direction = "added" if amount > 0 else "removed"
            print(f"[{item_name}] {direction} {abs(amount)}. New Total: {self.items[item_name]['Qty']} (Logged by {updated_by})")
        else:
            print(f"Error: {item_name} does not exist. Add it first.")

    def show_inventory(self):
        """Displays the current ledger."""
        print(f"{'Item':<20} | {'Category':<15} | {'Qty':<5} | {'Last Updated By':<15} | {'Date':<12}")
        print("-" * 75)
        
        for name, data in self.items.items():
            print(f"{name:<20} | {data['Category']:<15} | {data['Qty']:<5} | {data['Updated By']:<15} | {data['Date']:<12}")

# --- Execution ---

tracker = InventoryTracker()

# 1. Register items with a starting count
# tracker.add_item("2.1 Units", "Hardware", 20)

# 2. Log ins and outs (+ for in, - for out)
# tracker.record_movement("2.1 Units", -3, "Harrison")  
# tracker.record_movement("2.1 Units", 5, "Malavika")   

tracker.show_inventory()