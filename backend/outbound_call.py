import asyncio
import json
import os
import uuid

from dotenv import load_dotenv
from livekit import api


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env.local"))
load_dotenv(os.path.join(BASE_DIR, ".env"))


AGENT_NAME = os.getenv("AGENT_NAME", "my-agent")
TRUNK_ID = os.getenv("LIVEKIT_SIP_OUTBOUND_TRUNK_ID")


async def make_outbound_call(sip_user: str):
    if not TRUNK_ID:
        raise RuntimeError(
            "LIVEKIT_SIP_OUTBOUND_TRUNK_ID is not configured."
        )

    sip_user = sip_user.strip()

    if not sip_user:
        raise ValueError("SIP user cannot be empty.")

    room_name = f"healthaccess-outbound-{uuid.uuid4().hex[:10]}"

    metadata = json.dumps(
        {
            "phone_number": sip_user,
            "call_type": "medication_reminder",
        }
    )

    print()
    print("=" * 60)
    print("HEALTHACCESS SIP OUTBOUND CALL")
    print("=" * 60)
    print(f"Agent : {AGENT_NAME}")
    print(f"Room  : {room_name}")
    print(f"Target: {sip_user}")
    print(f"Trunk : {TRUNK_ID}")
    print("=" * 60)
    print()

    lkapi = api.LiveKitAPI()

    try:
        print("Starting HealthAccess agent...")

        dispatch = await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME,
                room=room_name,
                metadata=metadata,
            )
        )

        print("Agent dispatch created.")
        print(f"Dispatch ID: {dispatch.id}")

        participant_identity = (
            f"linphone-{uuid.uuid4().hex[:8]}"
        )

        print()
        print("Calling SIP destination...")

        participant = await lkapi.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=TRUNK_ID,
                sip_call_to=sip_user,
                room_name=room_name,
                participant_identity=participant_identity,
                participant_name="HealthAccess User",
                wait_until_answered=True,
            )
        )

        print()
        print("=" * 60)
        print("CALL CONNECTED")
        print("=" * 60)
        print(f"Participant: {participant}")
        print("=" * 60)
        print()

        return participant

    except Exception as exc:
        print()
        print("=" * 60)
        print("OUTBOUND CALL FAILED")
        print("=" * 60)
        print(str(exc))
        print("=" * 60)
        print()
        raise

    finally:
        await lkapi.aclose()


if __name__ == "__main__":
    sip_address = "swastikdubey"

    asyncio.run(
        make_outbound_call(sip_address)
    )