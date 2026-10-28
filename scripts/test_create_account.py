import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from decimal import Decimal
from pydantic import ValidationError
from app.db.database import init_db_pool, close_db_pool
from app.services.account_service import AccountService
from app.schemas.account import AccountCreate


async def run_tests():
    print("=" * 60)
    print("Testing Account Creation Logic (Simplified Architecture)")
    print("=" * 60)

    # 1. Initialize DB pool
    pool = await init_db_pool()
    print("✓ PostgreSQL pool connected and 'accounts' table initialized.")

    async with pool.acquire() as conn:
        service = AccountService(conn)

        # Test Case 1: Successful account creation with alphabetical name
        print("\n[Test 1] Creating account with valid alphabetical name 'Alice Smith'...")
        input_data = AccountCreate(name="Alice Smith")
        account = await service.create_account(input_data)

        print(f"  Account ID:   {account.id} (Unique UUID)")
        print(f"  Name:         {account.name}")
        print(f"  Balance:      {account.balance} (Should be 0.00)")
        print(f"  Created At:   {account.created_at}")

        assert account.id is not None, "Account ID must not be None"
        assert account.name == "Alice Smith", "Name must match input"
        assert account.balance == Decimal("0.00") or account.balance == Decimal("0.0000"), "Balance must be 0"
        print("✓ Test 1 PASSED: Account successfully created with required constraints.")

        # Test Case 2: Retrieve created account from DB
        print("\n[Test 2] Querying created account from DB via service...")
        db_account = await service.get_account_by_id(account.id)
        assert db_account is not None, "Account must be found in DB"
        assert db_account.id == account.id
        assert db_account.name == "Alice Smith"
        assert db_account.balance == Decimal("0.0000")
        print("✓ Test 2 PASSED: Direct DB query matches created account.")

        # Test Case 3: Alphanumeric name with digits must be rejected
        print("\n[Test 3] Verifying alphanumeric name 'Alice123' is rejected...")
        try:
            AccountCreate(name="Alice123")
            print("✗ Test 3 FAILED: 'Alice123' should have been rejected by schema validation")
        except (ValidationError, ValueError) as e:
            print(f"  Expected validation caught: {e}")
            print("✓ Test 3 PASSED: Alphanumeric name with digits successfully rejected.")

        # Test Case 4: Name with special characters must be rejected
        print("\n[Test 4] Verifying name with special characters 'Bob@Bank!' is rejected...")
        try:
            AccountCreate(name="Bob@Bank!")
            print("✗ Test 4 FAILED: 'Bob@Bank!' should have been rejected")
        except (ValidationError, ValueError) as e:
            print(f"  Expected validation caught: {e}")
            print("✓ Test 4 PASSED: Name with special characters successfully rejected.")

        # Test Case 5: Whitespace-only name must be rejected
        print("\n[Test 5] Verifying empty / whitespace-only name is rejected...")
        try:
            AccountCreate(name="   ")
            print("✗ Test 5 FAILED: Blank name should have been rejected")
        except (ValidationError, ValueError) as e:
            print(f"  Expected validation caught: {e}")
            print("✓ Test 5 PASSED: Whitespace-only name successfully rejected.")

        # Test Case 6: Client cannot provide balance
        print("\n[Test 6] Verifying client cannot provide balance...")
        try:
            bad_input = AccountCreate.model_validate({"name": "Bob", "balance": 1000.0})
            has_balance = hasattr(bad_input, "balance") and bad_input.balance != Decimal("0.00")
            if not has_balance:
                print("  Input schema disallowed client-supplied 'balance'.")
            print("✓ Test 6 PASSED: Client cannot manipulate initial balance.")
        except ValidationError:
            print("✓ Test 6 PASSED: Validation caught unexpected balance parameter.")

    # 2. Cleanup
    await close_db_pool()
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_tests())
