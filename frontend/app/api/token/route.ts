import { NextResponse } from 'next/server';
import { AccessToken, type AccessTokenOptions, type VideoGrant } from 'livekit-server-sdk';
import { RoomConfiguration } from '@livekit/protocol';
import { randomUUID } from 'crypto';

type ConnectionDetails = {
  serverUrl: string;
  roomName: string;
  participantName: string;
  participantToken: string;
};

const API_KEY = process.env.LIVEKIT_API_KEY;
const API_SECRET = process.env.LIVEKIT_API_SECRET;
const LIVEKIT_URL = process.env.LIVEKIT_URL;
const AGENT_NAME = process.env.AGENT_NAME;

export const revalidate = 0;

const CALLER_ID_COOKIE = 'medi_sathi_caller_id';

export async function POST(req: Request) {
  try {
    if (LIVEKIT_URL === undefined) {
      throw new Error('LIVEKIT_URL is not defined');
    }

    if (API_KEY === undefined) {
      throw new Error('LIVEKIT_API_KEY is not defined');
    }

    if (API_SECRET === undefined) {
      throw new Error('LIVEKIT_API_SECRET is not defined');
    }

    // Parse request body
    const body = await req.json().catch(() => ({}));

    let roomConfig: RoomConfiguration | undefined;

    if (body?.room_config) {
      roomConfig = RoomConfiguration.fromJson(body.room_config, {
        ignoreUnknownFields: true,
      });
    } else if (AGENT_NAME) {
      roomConfig = RoomConfiguration.fromJson(
        {
          agents: [{ agentName: AGENT_NAME }],
        },
        {
          ignoreUnknownFields: true,
        }
      );
    }

    /*
     * IMPORTANT:
     * Keep the caller ID stable between conversations.
     *
     * First visit:
     *   Generate a new ID and save it in a browser cookie.
     *
     * Later visits:
     *   Reuse the same ID.
     *
     * This allows the backend SQLite memory to recognize
     * the returning caller.
     */
    const requestCookies = req.headers.get('cookie') || '';

    const existingCookie = requestCookies
      .split(';')
      .map((cookie) => cookie.trim())
      .find((cookie) => cookie.startsWith(`${CALLER_ID_COOKIE}=`));

    let callerId: string;

    if (existingCookie) {
      callerId = decodeURIComponent(
        existingCookie.substring(`${CALLER_ID_COOKIE}=`.length)
      );
    } else {
      callerId = `caller_${randomUUID()}`;
    }

    const participantName =
      typeof body?.participantName === 'string' &&
      body.participantName.trim().length > 0
        ? body.participantName.trim()
        : 'user';

    /*
     * IMPORTANT:
     * This identity is now stable for the same browser.
     */
    const participantIdentity = callerId;

    // Room can still be different for every conversation.
    // The caller identity remains the same.
    const roomName = `voice_assistant_room_${randomUUID()}`;

    const participantToken = await createParticipantToken(
      {
        identity: participantIdentity,
        name: participantName,
      },
      roomName,
      roomConfig
    );

    const data: ConnectionDetails = {
      serverUrl: LIVEKIT_URL,
      roomName,
      participantName,
      participantToken,
    };

    const response = NextResponse.json(data, {
      headers: {
        'Cache-Control': 'no-store',
      },
    });

    /*
     * Save caller ID in browser.
     *
     * maxAge = 1 year
     * httpOnly = JavaScript cannot modify it
     * sameSite = protects against cross-site requests
     */
    if (!existingCookie) {
      response.cookies.set({
        name: CALLER_ID_COOKIE,
        value: callerId,
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax',
        maxAge: 60 * 60 * 24 * 365,
        path: '/',
      });
    }

    return response;
  } catch (error) {
    if (error instanceof Error) {
      console.error(error);
      return new NextResponse(error.message, {
        status: 500,
      });
    }

    return new NextResponse('Unknown error', {
      status: 500,
    });
  }
}

function createParticipantToken(
  userInfo: AccessTokenOptions,
  roomName: string,
  roomConfig?: RoomConfiguration
): Promise<string> {
  const at = new AccessToken(API_KEY, API_SECRET, {
    ...userInfo,
    ttl: '15m',
  });

  const grant: VideoGrant = {
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canPublishData: true,
    canSubscribe: true,
  };

  at.addGrant(grant);

  if (roomConfig) {
    at.roomConfig = roomConfig;
  }

  return at.toJwt();
}