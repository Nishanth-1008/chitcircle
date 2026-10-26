#!/usr/bin/env python3
"""Seed script to create demo circles, members, and cycles for testing."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uuid
from datetime import datetime, timedelta, timezone

from app.db import init_db, get_session
from app.models import Circle, Member, Cycle, RulesetRow
from app.presets import indian_auction_chit, tanda_rotation, agreed_discount_early_payout


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_db_session():
    """Get a database session from the generator."""
    gen = get_session()
    return next(gen)


def create_demo_data():
    """Create demo circles with members and cycles."""
    # Use SQLite for demo
    init_db("sqlite://")

    session = get_db_session()

    try:
        # Create organizer user
        organizer_id = "organizer-1"

        # Circle 1: Indian Auction Chit (20 members, 1 crore)
        print("Creating Indian Auction Chit circle...")
        circle1_id = str(uuid.uuid4())
        ruleset1 = indian_auction_chit(circle1_id, total_chit_value=10_000_000, member_count=20)

        session.add(Circle(id=circle1_id, name="Demo Indian Chit Fund", organizer_id=organizer_id))
        session.add(RulesetRow(
            circle_id=circle1_id, version=1, data=ruleset1.to_dict(),
            fingerprint=ruleset1.fingerprint(), status="ACTIVE",
            reason="Initial ruleset", created_by=organizer_id
        ))

        members1 = [
            Member(id=str(uuid.uuid4()), circle_id=circle1_id, name=f"Member {i+1}", position=i+1)
            for i in range(20)
        ]
        session.add_all(members1)
        session.commit()

        # Create first cycle
        due_date = _now() + timedelta(days=30)
        cycle1 = Cycle(circle_id=circle1_id, number=1, ruleset_version=1, due_date=due_date)
        session.add(cycle1)
        session.commit()

        print(f"  Circle ID: {circle1_id}")
        print(f"  Cycle ID: {cycle1.id}")
        print(f"  Members: {len(members1)}")

        # Circle 2: Tanda Rotation (10 members, $10k)
        print("\nCreating Tanda Rotation circle...")
        circle2_id = str(uuid.uuid4())
        ruleset2 = tanda_rotation(circle2_id, total_chit_value=10_000, member_count=10)

        session.add(Circle(id=circle2_id, name="Demo Tanda Circle", organizer_id=organizer_id))
        session.add(RulesetRow(
            circle_id=circle2_id, version=1, data=ruleset2.to_dict(),
            fingerprint=ruleset2.fingerprint(), status="ACTIVE",
            reason="Initial ruleset", created_by=organizer_id
        ))

        members2 = [
            Member(id=str(uuid.uuid4()), circle_id=circle2_id, name=f"Tanda Member {i+1}", position=i+1)
            for i in range(10)
        ]
        session.add_all(members2)
        session.commit()

        due_date2 = _now() + timedelta(days=14)
        cycle2 = Cycle(circle_id=circle2_id, number=1, ruleset_version=1, due_date=due_date2)
        session.add(cycle2)
        session.commit()

        print(f"  Circle ID: {circle2_id}")
        print(f"  Cycle ID: {cycle2.id}")
        print(f"  Members: {len(members2)}")

        # Circle 3: Agreed Discount Early Payout (10 members, $50k)
        print("\nCreating Agreed Discount Early Payout circle...")
        circle3_id = str(uuid.uuid4())
        ruleset3 = agreed_discount_early_payout(circle3_id, total_chit_value=50_000, member_count=10)

        session.add(Circle(id=circle3_id, name="Demo Early Payout Circle", organizer_id=organizer_id))
        session.add(RulesetRow(
            circle_id=circle3_id, version=1, data=ruleset3.to_dict(),
            fingerprint=ruleset3.fingerprint(), status="ACTIVE",
            reason="Initial ruleset", created_by=organizer_id
        ))

        members3 = [
            Member(id=str(uuid.uuid4()), circle_id=circle3_id, name=f"Early Member {i+1}", position=i+1)
            for i in range(10)
        ]
        session.add_all(members3)
        session.commit()

        due_date3 = _now() + timedelta(days=30)
        cycle3 = Cycle(circle_id=circle3_id, number=1, ruleset_version=1, due_date=due_date3)
        session.add(cycle3)
        session.commit()

        print(f"  Circle ID: {circle3_id}")
        print(f"  Cycle ID: {cycle3.id}")
        print(f"  Members: {len(members3)}")

        print("\n✅ Demo data created successfully!")
        print(f"\nCircle IDs:")
        print(f"  Indian Chit: {circle1_id}")
        print(f"  Tanda: {circle2_id}")
        print(f"  Early Payout: {circle3_id}")

    except Exception as e:
        session.rollback()
        print(f"❌ Error creating demo data: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    create_demo_data()