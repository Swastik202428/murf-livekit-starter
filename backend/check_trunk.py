import asyncio
from dotenv import load_dotenv
from livekit import api

load_dotenv(".env.local")
load_dotenv(".env")


async def main():
    lk = api.LiveKitAPI()

    try:
        result = await lk.sip.list_sip_outbound_trunk(
            api.ListSIPOutboundTrunkRequest()
        )

        print("=" * 60)
        print("OUTBOUND SIP TRUNK")
        print("=" * 60)
        print(result)
        print("=" * 60)

    finally:
        await lk.aclose()


if __name__ == "__main__":
    asyncio.run(main())