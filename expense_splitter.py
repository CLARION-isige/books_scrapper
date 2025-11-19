"""
Expense Splitter - Minimize transactions to settle debts among friends.

Algorithm:
1. Calculate each person's total expenses paid
2. Calculate the average expense per person (total / num_people)
3. Calculate each person's balance (what they paid - average)
4. Match creditors (positive balance) with debtors (negative balance)
5. Use greedy approach to minimize number of transactions
"""

from typing import Dict, List, Tuple
from collections import defaultdict


class ExpenseSplitter:
    """Splits expenses among friends with minimal transactions."""
    
    def __init__(self):
        self.expenses: Dict[str, float] = defaultdict(float)
        
    def add_expense(self, person: str, amount: float) -> None:
        """
        Record an expense paid by a person.
        
        Args:
            person: Name of the person who paid
            amount: Amount paid
        """
        if amount < 0:
            raise ValueError("Amount must be non-negative")
        self.expenses[person] += amount
    
    def calculate_balances(self) -> Dict[str, float]:
        """
        Calculate each person's balance (what they paid - fair share).
        
        Returns:
            Dictionary mapping person to their balance
            Positive = they are owed money
            Negative = they owe money
        """
        if not self.expenses:
            return {}
        
        total_expenses = sum(self.expenses.values())
        num_people = len(self.expenses)
        fair_share = total_expenses / num_people
        
        balances = {}
        for person, paid in self.expenses.items():
            balances[person] = round(paid - fair_share, 2)
        
        return balances
    
    def settle_debts(self) -> List[Tuple[str, str, float]]:
        """
        Calculate minimal transactions to settle all debts.
        
        Returns:
            List of tuples (debtor, creditor, amount)
            Each tuple means: debtor pays creditor the amount
        """
        balances = self.calculate_balances()
        
        if not balances:
            return []
        
        # Separate into creditors (owed money) and debtors (owe money)
        creditors = [(person, balance) for person, balance in balances.items() if balance > 0.01]
        debtors = [(person, -balance) for person, balance in balances.items() if balance < -0.01]
        
        # Sort by amount (largest first) for greedy matching
        creditors.sort(key=lambda x: x[1], reverse=True)
        debtors.sort(key=lambda x: x[1], reverse=True)
        
        transactions = []
        i, j = 0, 0
        
        while i < len(debtors) and j < len(creditors):
            debtor, debt_amount = debtors[i]
            creditor, credit_amount = creditors[j]
            
            # Transfer the minimum of what debtor owes and creditor is owed
            transfer_amount = min(debt_amount, credit_amount)
            
            transactions.append((debtor, creditor, round(transfer_amount, 2)))
            
            # Update remaining amounts
            debtors[i] = (debtor, debt_amount - transfer_amount)
            creditors[j] = (creditor, credit_amount - transfer_amount)
            
            # Move to next debtor/creditor if fully settled
            if debtors[i][1] < 0.01:
                i += 1
            if creditors[j][1] < 0.01:
                j += 1
        
        return transactions
    
    def print_summary(self) -> None:
        """Print a detailed summary of expenses and settlements."""
        if not self.expenses:
            print("No expenses recorded.")
            return
        
        print("\n" + "="*60)
        print("EXPENSE SUMMARY")
        print("="*60)
        
        total = sum(self.expenses.values())
        fair_share = total / len(self.expenses)
        
        print(f"\nTotal expenses: ${total:.2f}")
        print(f"Number of people: {len(self.expenses)}")
        print(f"Fair share per person: ${fair_share:.2f}")
        
        print("\n" + "-"*60)
        print("WHO PAID WHAT:")
        print("-"*60)
        for person, amount in sorted(self.expenses.items()):
            print(f"  {person:20s} paid ${amount:8.2f}")
        
        print("\n" + "-"*60)
        print("BALANCES:")
        print("-"*60)
        balances = self.calculate_balances()
        for person, balance in sorted(balances.items(), key=lambda x: x[1], reverse=True):
            if balance > 0.01:
                print(f"  {person:20s} is owed ${balance:8.2f}")
            elif balance < -0.01:
                print(f"  {person:20s} owes ${-balance:8.2f}")
            else:
                print(f"  {person:20s} is settled")
        
        print("\n" + "="*60)
        print("SETTLEMENT TRANSACTIONS (MINIMIZED)")
        print("="*60)
        
        transactions = self.settle_debts()
        if not transactions:
            print("\nNo transactions needed - everyone is settled!")
        else:
            print(f"\nMinimum {len(transactions)} transaction(s) needed:\n")
            for i, (debtor, creditor, amount) in enumerate(transactions, 1):
                print(f"  {i}. {debtor} pays {creditor} ${amount:.2f}")
        
        print("\n" + "="*60 + "\n")


def example_usage():
    """Example usage with a trip scenario."""
    splitter = ExpenseSplitter()
    
    # Example: 4 friends on a trip
    splitter.add_expense("Alice", 150.00)  # Paid for hotel
    splitter.add_expense("Bob", 80.00)     # Paid for gas
    splitter.add_expense("Charlie", 45.00) # Paid for breakfast
    splitter.add_expense("Diana", 125.00)  # Paid for dinners
    
    splitter.print_summary()


def interactive_mode():
    """Interactive mode to input expenses."""
    print("\n" + "="*60)
    print("EXPENSE SPLITTER - Interactive Mode")
    print("="*60)
    
    splitter = ExpenseSplitter()
    
    num_people = int(input("\nHow many people went on the trip? "))
    
    print(f"\nEnter expenses paid by each person (0 if nothing):\n")
    
    for i in range(num_people):
        person = input(f"Person {i+1} name: ").strip()
        amount = float(input(f"  Amount paid by {person}: $"))
        if amount > 0:
            splitter.add_expense(person, amount)
    
    splitter.print_summary()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        interactive_mode()
    else:
        example_usage()
        print("\nTip: Run with --interactive flag for custom input")
        print("     python expense_splitter.py --interactive")
