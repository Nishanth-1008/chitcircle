#!/usr/bin/env python3
"""Simulator to drive a circle through multiple cycles via the API."""

import sys
import os
import time
import random
import uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.main import create_app
from app.db import init_db, get_session
from app.services.gateway import MockGateway, get_gateway
from app.models import User


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_simulation(num_cycles: int = 20, num_members: int = 20):
    """Run a full simulation of a circle through multiple cycles."""

    # Set webhook secret for test environment
    os.environ["WEBHOOK_SECRET"] = "test-secret"
    os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-simulation"
    os.environ["JWT_ALGORITHM"] = "HS256"
    os.environ["JWT_EXPIRATION_MINUTES"] = "60"

    # Initialize database
    init_db("sqlite://")

    # Create app with mock gateway
    app = create_app()
    mock_gateway = MockGateway()
    app.dependency_overrides[get_gateway] = lambda: mock_gateway

    client = TestClient(app)
    client.gw = mock_gateway

    # Create users in database first
    session_gen = get_session()
    session = next(session_gen)
    try:
        # Create organizer
        organizer_id = str(uuid.uuid4())
        organizer = User(
            id=organizer_id,
            email="organizer@test.com",
            hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj/RK.PZvO.S",  # "password"
            name="Organizer",
            role="organizer",
            is_active=True,
        )
        session.add(organizer)

        # Create approvers
        approver1_id = str(uuid.uuid4())
        approver1 = User(
            id=approver1_id,
            email="approver1@test.com",
            hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj/RK.PZvO.S",
            name="Approver 1",
            role="approver",
            is_active=True,
        )
        session.add(approver1)

        approver2_id = str(uuid.uuid4())
        approver2 = User(
            id=approver2_id,
            email="approver2@test.com",
            hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj/RK.PZvO.S",
            name="Approver 2",
            role="approver",
            is_active=True,
        )
        session.add(approver2)

        # Create members
        member_ids = []
        for i in range(num_members):
            member_id = str(uuid.uuid4())
            member_ids.append(member_id)
            member = User(
                id=member_id,
                email=f"member{i+1}@test.com",
                hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj/RK.PZvO.S",
                name=f"Member {i+1}",
                role="member",
                is_active=True,
            )
            session.add(member)

        session.commit()
    finally:
        session.close()

    # Login to get JWT tokens
    def login(email: str, password: str = "password") -> str:
        r = client.post("/auth/login", data={"username": email, "password": password})
        assert r.status_code == 200, f"Login failed: {r.text}"
        return r.json()["access_token"]

    org_token = login("organizer@test.com")
    approver1_token = login("approver1@test.com")
    approver2_token = login("approver2@test.com")

    ORG = {"Authorization": f"Bearer {org_token}"}
    APPROVER1 = {"Authorization": f"Bearer {approver1_token}"}
    APPROVER2 = {"Authorization": f"Bearer {approver2_token}"}

    # Create circle
    print(f"Creating circle with {num_members} members...")
    member_names = [f"Member {i+1}" for i in range(num_members)]

    # Use Indian auction chit ruleset
    # Use a chit value divisible by num_members (e.g., 6 members -> 12,000,000)
    chit_value = 1_000_000 * num_members  # Makes it divisible

    ruleset = {
        "total_chit_value": chit_value,
        "member_count": num_members,
        "currency": "INR",
        "payout_mode": "SEALED_BID_AUCTION",
        "effective_date": datetime.now(timezone.utc).date().isoformat(),
        "auction": {
            "max_discount_rate": "0.30",
            "tie_break": "EARLIEST_BID",
            "no_bid_fallback": "FIXED_ROTATION",
            "min_discount": 0,
            "increment": 10000,
        },
        "dividend": {
            "allocation": "ELIGIBLE_MEMBERS",
        },
        "grace_period_days": 3,
        "commission": {"base": "PERCENT_OF_CHIT_VALUE", "rate": 0.05, "rounding": "HALF_UP"},
        "rounding": {
            "contribution_remainder": "REJECT",
            "remainder_destination": "ORGANIZER",
        },
        "one_win_per_member": True,
        "require_full_collection_before_payout": True,
        "required_approvals": 2,
        "no_bid_fallback": "FIXED_ROTATION",
        "jurisdiction_profile": "INDIA_CHA",
        "allow_agreed_discount": True,
        "require_security": False,
        "early_payout_min_consent_rate": "0.75",
    }

    r = client.post("/circles", json={
        "name": "Simulation Circle",
        "ruleset": ruleset,
        "members": member_names
    }, headers=ORG)
    assert r.status_code == 201, f"Circle creation failed: {r.text}"
    circle = r.json()
    circle_id = circle["id"]
    print(f"Circle created: {circle_id}")

    # Store member IDs by position
    members_by_position = {m["position"]: m["id"] for m in circle["members"]}

    # Run cycles
    for cycle_num in range(1, num_cycles + 1):
        print(f"\n{'='*60}")
        print(f"CYCLE {cycle_num}")
        print(f"{'='*60}")

        # Create cycle
        due_date = (_now() + timedelta(days=30)).isoformat()
        r = client.post(f"/circles/{circle_id}/cycles", json={
            "due_date": due_date
        }, headers=ORG)
        assert r.status_code == 201, f"Cycle creation failed: {r.text}"
        cycle = r.json()
        cycle_id = cycle["id"]
        print(f"Cycle created: {cycle_id}")

        # Open cycle
        r = client.post(f"/cycles/{cycle_id}/open", headers=ORG)
        assert r.status_code == 200, f"Open cycle failed: {r.text}"
        print("Cycle opened - obligations created")

        # Get obligations
        r = client.get(f"/cycles/{cycle_id}", headers=ORG)
        cycle_data = r.json()
        obligations = cycle_data["obligations"]

        # Simulate payments from all members
        print("\nSimulating payments...")
        for ob in obligations:
            member_id = ob["member_id"]
            net_payable = ob["net_payable"]

            # Skip if already won (they don't pay in later cycles)
            # Actually in chit funds, winners still contribute but receive dividend

            # Simulate payment via webhook
            txn_id = f"pay-{cycle_id}-{member_id}"
            webhook_payload = {
                "provider_txn_id": txn_id,
                "kind": "PAYMENT",
                "status": "COMPLETED",
                "amount": net_payable,
                "currency": "INR",
                "cycle_id": cycle_id,
                "member_id": member_id
            }

            # Sign with HMAC
            import json
            from financial_engine.reconciliation import HmacVerifier
            body = json.dumps(webhook_payload).encode()
            headers = {"Content-Type": "application/json", "X-Signature": HmacVerifier("test-secret").sign(body)}

            r = client.post("/webhooks/provider", content=body, headers=headers)
            if r.status_code != 200:
                print(f"  ⚠️ Payment failed for {member_id}: {r.text}")

        print("All payments processed")

        # Run auction
        print("\nRunning auction...")
        r = client.post(f"/cycles/{cycle_id}/auction/open", headers=ORG)
        assert r.status_code == 200, f"Auction open failed: {r.text}"

        # Determine eligible bidders (those who haven't won yet)
        circle_info = client.get(f"/circles/{circle_id}", headers=ORG).json()
        eligible_bidders = [m for m in circle_info["members"] if not m["has_won"]]

        # Login for members to get their tokens
        member_tokens = {}
        for i in range(num_members):
            member_tokens[f"member{i+1}@test.com"] = login(f"member{i+1}@test.com")

        if eligible_bidders:
            # Random bids from eligible members
            bids = []
            for i, member in enumerate(eligible_bidders):
                if i < 3:  # Only first 3 bid for simulation
                    # Bid between 5% and 25% discount
                    discount = random.randint(500_000, 2_500_000)
                    member_email = f"member{member['position']}@test.com"
                    member_headers = {"Authorization": f"Bearer {member_tokens[member_email]}"}
                    r = client.post(f"/cycles/{cycle_id}/auction/bids", json={
                        "member_id": member["id"],
                        "discount": discount
                    }, headers=member_headers)
                    if r.status_code == 200 and r.json().get("accepted"):
                        bids.append((member["id"], discount))
                        print(f"  Bid accepted: {member['name']} - {discount/10000:.2f}% discount")

        # Close auction
        r = client.post(f"/cycles/{cycle_id}/auction/close", headers=ORG)
        assert r.status_code == 200, f"Auction close failed: {r.text}"
        auction_result = r.json()
        print(f"Auction result: {auction_result.get('status', 'N/A')}")
        if auction_result.get("winner_member_id"):
            winner_name = next(m["name"] for m in circle_info["members"] if m["id"] == auction_result["winner_member_id"])
            print(f"Winner: {winner_name} with {auction_result.get('discount', 0)/10000:.2f}% discount")

        # Calculate settlement
        r = client.post(f"/cycles/{cycle_id}/settlement", headers=ORG)
        assert r.status_code == 201, f"Settlement failed: {r.text}"
        settlement = r.json()
        print("Settlement calculated")

        # Approve settlement (need 2 approvals from different approvers)
        print("\nApproving settlement...")
        approvers = [APPROVER1, APPROVER2]
        for i, approver_headers in enumerate(approvers):
            r = client.post(f"/settlements/{settlement['id']}/approvals", json={
                "decision": "APPROVE",
                "reason": f"Approval {i+1}"
            }, headers=approver_headers)
            assert r.status_code == 200, f"Approval failed: {r.text}"

        # Execute payout
        print("Executing payout...")
        r = client.post(f"/settlements/{settlement['id']}/payout", headers=ORG)
        if r.status_code == 200:
            payout_result = r.json()
            print(f"Payout result: {payout_result.get('outcome', 'N/A')}")

            # Check payout status
            if payout_result.get("outcome") == "SUBMITTED":
                # Simulate provider callback for payout confirmation
                payout_txn = f"payout-{settlement['id']}"
                payout_amount = settlement["settlement"]["winner_payout"]["minor"]

                payout_payload = {
                    "provider_txn_id": payout_txn,
                    "kind": "PAYOUT",
                    "status": "COMPLETED",
                    "amount": payout_amount,
                    "currency": "INR",
                    "payout_reference": settlement["payout_reference"]
                }

                body = json.dumps(payout_payload).encode()
                headers = {"Content-Type": "application/json", "X-Signature": HmacVerifier("test-secret").sign(body)}

                r = client.post("/webhooks/provider", content=body, headers=headers)
                if r.status_code == 200:
                    print("Payout confirmed via webhook")

        # Finalize
        r = client.post(f"/settlements/{settlement['id']}/finalize", headers=ORG)
        if r.status_code == 200:
            print("Cycle finalized ✓")
        else:
            print(f"Finalization failed: {r.text}")
            # Check reconciliation
            r = client.get(f"/settlements/{settlement['id']}/reconciliation", headers=ORG)
            print(f"Reconciliation: {r.json()}")

    print(f"\n{'='*60}")
    print(f"SIMULATION COMPLETE: {num_cycles} cycles processed")
    print(f"{'='*60}")

    # Show final circle state
    final_circle = client.get(f"/circles/{circle_id}", headers=ORG).json()
    print(f"\nFinal member states:")
    for m in final_circle["members"]:
        print(f"  {m['name']}: won={m['has_won']}, security={m['security_status']}")


if __name__ == "__main__":
    run_simulation(num_cycles=5, num_members=6)  # Smaller for quick test