"""Debug test to check transaction state."""

import pytest
from sqlalchemy import text


class TestTransactionDebug:
    """Tests to debug transaction state."""

    @pytest.mark.asyncio
    async def test_check_transaction_state(self, db_context):
        """Check the transaction state in the test."""
        print("\n=== Checking transaction state ===")
        
        # Get the session from db_context
        session = db_context.session
        
        # Check if we're in a transaction
        print(f"In transaction: {session.in_transaction()}")
        print(f"Is active: {session.is_active}")
        
        # Check the current transaction ID
        result = await session.execute(text("SELECT txid_current()"))
        txid = result.scalar()
        print(f"Transaction ID: {txid}")
        
        # Create an exchange
        exchange = await db_context.exchanges.create_cat_exchange(
            name="test_exchange",
            ohlcv_view=""
        )
        await db_context.flush()
        print(f"Created exchange with ID: {exchange.cat_ex_id}")
        
        # Check data is visible in same transaction
        result = await session.execute(text("SELECT COUNT(*) FROM cat_exchanges"))
        count = result.scalar()
        print(f"Exchanges in database (same transaction): {count}")

    @pytest.mark.asyncio
    async def test_second_transaction(self, db_context):
        """Check if data persists to second test."""
        print("\n=== Second test transaction ===")
        
        session = db_context.session
        
        # Check transaction ID - should be different
        result = await session.execute(text("SELECT txid_current()"))
        txid = result.scalar()
        print(f"Transaction ID: {txid}")
        
        # Check if previous test's data is visible
        result = await session.execute(text("SELECT COUNT(*) FROM cat_exchanges"))
        count = result.scalar()
        print(f"Exchanges in database (new transaction): {count}")
        
        # Try to list exchanges
        exchanges = await db_context.exchanges.get_cat_exchanges()
        print(f"Exchange names: {[e.name for e in exchanges]}")