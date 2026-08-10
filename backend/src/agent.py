import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    function_tool,
    room_io,
    tokenize,
)
from livekit.plugins import (
    deepgram,
    google,
    murf,
    noise_cancellation,
    silero,
)
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from .caller_memory import init_db, lookup_caller, save_caller


# ============================================================
# ENVIRONMENT
# ============================================================

# Load backend/.env.local first
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env.local")
load_dotenv(BASE_DIR / ".env")


# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("agent")


# ============================================================
# CONFIGURATION
# ============================================================

DATA_DIR = BASE_DIR / "data"

FACILITIES_FILE = DATA_DIR / "health_facilities.json"

NOMINATIM_SEARCH_URL = (
    "https://nominatim.openstreetmap.org/search"
)

DB_CONN = init_db()


# ============================================================
# MEDISATHI SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are MediSathi, an AI-powered Healthcare Voice Assistant.

Your job is to make healthcare information simple, safe, accessible,
and easy to understand through natural voice conversations.

You are friendly, calm, patient, empathetic, and professional.

You are NOT a doctor.

You must never diagnose a disease, prescribe medication, recommend
medication dosages, or replace a qualified healthcare professional.

Do not use emojis in spoken responses.
Do not use markdown in spoken responses.
Keep responses short, clear, natural, and easy to understand.

============================================================
FIRST GREETING
============================================================

When the conversation begins, say:

"Hello! I'm MediSathi, your AI Healthcare Voice Assistant. Namaste!
I can help you understand common health concerns and guide you
toward appropriate care. How can I help you today?"

Do not repeat the full greeting later.

============================================================
DAY 5 TOOL
============================================================

You have access to a healthcare tool called:

get_health_triage_and_facility

This tool:

1. Reads the symptoms provided by the user.
2. Determines a general urgency level.
3. Can use the user's location.
4. Looks up a healthcare facility from the local MediSathi dataset.
5. Can use OpenStreetMap Nominatim to understand the location.
6. Returns the source and date of the information.

The healthcare facility dataset is LOCAL.
It is NOT a live medical database.

============================================================
WHEN TO USE THE TOOL
============================================================

Use get_health_triage_and_facility when the user:

- Describes one or more symptoms.
- Asks how serious symptoms may be.
- Asks how urgent symptoms may be.
- Asks whether they should seek medical care.
- Asks for a nearby healthcare facility.
- Gives symptoms together with a location.

Examples:

"I have a fever."

"I have chest pain."

"I'm having difficulty breathing."

"I have a headache. Should I see a doctor?"

"I have fever and difficulty breathing."

"I have chest pain and I am in Lucknow."

When a location is given, pass it to the tool.

Do not invent a location.

============================================================
WHEN NOT TO USE THE TOOL
============================================================

Do not use the tool for:

- Greetings.
- Casual conversation.
- Non-health questions.
- Unrelated questions.
- Questions that do not require symptom assessment.

============================================================
TOOL INPUT
============================================================

Only provide symptoms that the user actually mentioned.

Never invent symptoms.

Never invent medical history.

If the user provides a location, pass that location.

============================================================
TOOL RESULT
============================================================

Never read raw JSON to the user.

Never read technical field names such as:

triage_level
data_source
facility_available

Translate the result into natural language.

For example:

"Based on the health information available to me, this may need
prompt medical attention."

============================================================
TRIAGE LEVELS
============================================================

Possible guidance levels:

Self-care / general guidance
Routine healthcare consultation
Prompt medical consultation
Emergency care

These are general guidance levels only.

They are NOT diagnoses.

============================================================
EMERGENCY
============================================================

Treat these symptoms as potentially serious:

- Chest pain.
- Difficulty breathing.
- Shortness of breath.
- Severe bleeding.
- Loss of consciousness.
- Seizure.
- Stroke-like symptoms.
- Severe poisoning.
- Suicidal thoughts.
- Severe burns.
- Severe or rapidly worsening symptoms.

If the tool returns Emergency care:

Be direct and concise.

Say:

"These symptoms may indicate a potentially serious situation.
Please seek emergency medical care immediately."

Do not ask unnecessary questions during an obvious emergency.

Do not diagnose the underlying condition.

============================================================
UNKNOWN INFORMATION
============================================================

If the tool cannot determine an appropriate result, do not guess.

Say:

"I don't have enough information in my current health dataset to
safely assess the urgency of these symptoms."

Then recommend professional medical advice when appropriate.

============================================================
TOOL FAILURE
============================================================

If the health data source or location lookup fails:

Do NOT:

- Invent a result.
- Guess a triage level.
- Invent a facility.
- Pretend the tool worked.
- Read technical errors.

Instead say:

"I'm sorry, my health information source is temporarily unavailable,
so I can't safely assess the situation using my current data.
If your symptoms are severe, rapidly worsening, or concerning,
please seek professional medical care."

============================================================
DATA FRESHNESS
============================================================

MediSathi currently uses a local dataset.

Never call this live medical data.

If data_as_of is available, mention it when useful.

For example:

"This information comes from MediSathi's local dataset, last updated
on August 10, 2026."

Never claim that this is government or hospital live data.

============================================================
FACILITY INFORMATION
============================================================

If a facility is returned:

Explain it naturally.

For example:

"I found a healthcare facility in the available local dataset."

Never invent:

- Facility names.
- Addresses.
- Distances.
- Phone numbers.

If no facility is available, say so honestly.

============================================================
FOLLOW-UP QUESTIONS
============================================================

When necessary, ask about:

- Main symptoms.
- Duration.
- Severity.
- Whether symptoms are getting better or worse.
- Relevant existing conditions.
- Current medications.
- Allergies.
- Age when relevant.

Ask one important question at a time.

If there is an obvious emergency, prioritize emergency guidance.

============================================================
MEMORY
============================================================

MediSathi can use caller memory.

Use remembered information only when relevant.

Current information from the user always takes priority.

Use save_caller only when the caller has explicitly agreed to
remember information.

============================================================
LANGUAGE
============================================================

The user may speak English, Hindi, or Hinglish.

Respond in the language the user naturally uses.

If the user speaks Hindi or Hinglish, respond naturally in Hindi
or Hinglish.

Use simple conversational Hindi.

Example:

User:
"Mujhe bukhar hai aur saans lene mein dikkat ho rahi hai."

Response:

"Saans lene mein dikkat ke saath bukhar ko lightly nahi lena chahiye.
Available health information ke according, ye emergency ho sakti hai.
Please turant emergency medical care lein."

============================================================
NATURAL VOICE
============================================================

Keep responses:

- Short.
- Clear.
- Natural.
- Conversational.
- Easy to understand.

Do not read JSON.

Do not read Python code.

Do not mention internal function names unless the user asks.

Instead of:

"I am calling get_health_triage_and_facility."

Say:

"Let me check the health information I have for those symptoms."

============================================================
NO HALLUCINATION
============================================================

If you do not know something, say so.

If the local dataset does not contain enough information, say so.

If a tool fails, say so.

Never invent medical facts.

Never invent a facility.

Never invent a triage result.

============================================================
OUT OF SCOPE
============================================================

For trading, cryptocurrency, politics, finance, gambling, hacking,
legal advice, or unrelated topics, say:

"My primary role is healthcare assistance, so I can't provide reliable
advice on that topic. If you have a health-related question, I'd be
happy to help."

============================================================
FINAL RULE
============================================================

MediSathi's goal is not to diagnose.

Its goal is:

Listen -> Understand -> Use the appropriate healthcare tool ->
Explain the result safely -> Guide the user toward appropriate care.

Always prioritize safety, honesty, clarity, and natural conversation.
"""


# ============================================================
# ASSISTANT
# ============================================================

class Assistant(Agent):

    def __init__(self, memory_context: str = "") -> None:

        instructions = SYSTEM_PROMPT

        if memory_context:
            instructions += f"""

============================================================
CURRENT CALLER MEMORY
============================================================

The following information was retrieved from the caller's
previous conversations.

Use it only when relevant.

Do not invent additional information.

{memory_context}

============================================================
END CALLER MEMORY
============================================================
"""

        super().__init__(
            instructions=instructions
        )

    # ========================================================
    # LOOKUP CALLER
    # ========================================================

    @function_tool
    async def lookup_caller(
        self,
        context: RunContext,
        user_id: str | None = None,
    ):
        """
        Look up a caller's saved profile.
        """

        if user_id is None:

            try:
                userdata = context.userdata
            except Exception:
                userdata = None

            if isinstance(userdata, dict):
                user_id = userdata.get("caller_id")

        if not user_id:
            return {
                "found": False,
                "reason": "missing user_id",
            }

        record = lookup_caller(
            DB_CONN,
            user_id,
        )

        if not record:
            return {
                "found": False,
                "user_id": user_id,
            }

        return {
            "found": True,
            **record,
        }

    # ========================================================
    # SAVE CALLER
    # ========================================================

    @function_tool
    async def save_caller(
        self,
        context: RunContext,
        user_id: str | None = None,
        name: str | None = None,
        language_preference: str | None = None,
        facts: dict[str, str] | None = None,
    ):
        """
        Save safe caller information after explicit consent.
        """

        if user_id is None:

            try:
                userdata = context.userdata
            except Exception:
                userdata = None

            if isinstance(userdata, dict):
                user_id = userdata.get("caller_id")

        if not user_id:
            return {
                "saved": False,
                "reason": "missing user_id",
            }

        record = save_caller(
            DB_CONN,
            user_id=user_id,
            name=name,
            language_preference=language_preference,
            facts=facts,
        )

        logger.info(
            "Caller memory saved for user_id=%s",
            user_id,
        )

        return {
            "saved": True,
            **record,
        }

    # ========================================================
    # DAY 5 HEALTH TOOL
    # ========================================================

    @function_tool
    async def get_health_triage_and_facility(
        self,
        context: RunContext,
        symptoms: str,
        location: str | None = None,
    ):
        """
        Assess the general urgency of the user's symptoms and,
        when possible, find a healthcare facility.

        Use this tool when the user describes symptoms and asks
        about seriousness, urgency, medical attention, or a
        nearby healthcare facility.

        This tool does not diagnose diseases.

        The data is based on the MediSathi local dataset.
        """

        logger.info(
            "DAY 5 TOOL CALLED | symptoms=%s | location=%s",
            symptoms,
            location,
        )

        try:

            symptoms_lower = (
                symptoms.strip().lower()
            )

            triage_level, triage_reason = (
                self._determine_triage(
                    symptoms_lower
                )
            )

            facility_result = (
                self._lookup_nearest_facility(
                    location
                )
            )

            result = {
                "success": True,
                "triage_level": triage_level,
                "triage_reason": triage_reason,
                "symptoms": symptoms,
                "location": location,
                "data_source": facility_result.get(
                    "data_source",
                    "MediSathi local dataset",
                ),
                "data_as_of": facility_result.get(
                    "data_as_of",
                    date.today().isoformat(),
                ),
            }

            result.update(facility_result)

            logger.info(
                "DAY 5 TOOL RESULT | %s",
                result,
            )

            return result

        except Exception:

            logger.exception(
                "DAY 5 HEALTH TOOL FAILED"
            )

            return {
                "success": False,
                "error": "health_data_unavailable",
                "message": (
                    "The MediSathi health information source "
                    "is temporarily unavailable."
                ),
                "data_source": (
                    "MediSathi local dataset"
                ),
                "data_as_of": date.today().isoformat(),
            }

    # ========================================================
    # TRIAGE LOGIC
    # ========================================================

    def _determine_triage(
        self,
        symptoms: str,
    ) -> tuple[str, str]:

        emergency_keywords = [
            "chest pain",
            "chest pressure",
            "chest tightness",
            "shortness of breath",
            "difficulty breathing",
            "breathing difficulty",
            "cannot breathe",
            "can't breathe",
            "severe bleeding",
            "unconscious",
            "loss of consciousness",
            "seizure",
            "poisoning",
            "suicidal",
            "suicide",
            "severe burn",
            "stroke",
            "face drooping",
            "slurred speech",
        ]

        prompt_keywords = [
            "high fever",
            "persistent fever",
            "fever for",
            "blood in",
            "vomiting",
            "vomit",
            "severe pain",
            "confusion",
            "dizziness",
            "faint",
            "fainting",
            "dehydration",
            "severe headache",
            "head injury",
            "pregnant",
            "pregnancy",
            "severe weakness",
        ]

        routine_keywords = [
            "fever",
            "cold",
            "cough",
            "headache",
            "sore throat",
            "runny nose",
            "sneezing",
            "mild pain",
        ]

        # Emergency first
        for keyword in emergency_keywords:

            if keyword in symptoms:

                return (
                    "Emergency care",
                    (
                        "The symptoms include serious warning signs "
                        "that may need immediate medical attention."
                    ),
                )

        # Prompt medical consultation
        for keyword in prompt_keywords:

            if keyword in symptoms:

                return (
                    "Prompt medical consultation",
                    (
                        "These symptoms may require a prompt "
                        "consultation with a healthcare professional."
                    ),
                )

        # Fever + cough
        if (
            "fever" in symptoms
            and "cough" in symptoms
        ):

            return (
                "Prompt medical consultation",
                (
                    "Fever combined with respiratory symptoms "
                    "may need prompt medical attention."
                ),
            )

        # Routine symptoms
        for keyword in routine_keywords:

            if keyword in symptoms:

                return (
                    "Routine healthcare consultation",
                    (
                        "The symptoms may be suitable for routine "
                        "healthcare guidance, but professional care "
                        "is recommended if they persist or worsen."
                    ),
                )

        return (
            "Routine healthcare consultation",
            (
                "Based on the symptoms described, consider speaking "
                "with a healthcare professional if the problem "
                "continues, worsens, or causes concern."
            ),
        )

    # ========================================================
    # FACILITY LOOKUP
    # ========================================================

    def _lookup_nearest_facility(
        self,
        location: str | None,
    ) -> dict:

        facility_data = (
            self._load_local_facilities()
        )

        if not facility_data:

            return {
                "facility_available": False,
                "facility_message": (
                    "No local healthcare facility data is available."
                ),
                "data_source": (
                    "MediSathi local dataset"
                ),
                "data_as_of": date.today().isoformat(),
            }

        if location:

            lookup = (
                self._lookup_facility_by_location(
                    location,
                    facility_data,
                )
            )

            if lookup.get(
                "facility_available"
            ):
                return lookup

        default = facility_data[0]

        return {
            "facility_available": True,
            "facility_name": default.get(
                "name",
                "Healthcare facility",
            ),
            "facility_address": default.get(
                "address",
                "Address unavailable",
            ),
            "distance_km": default.get(
                "distance_km",
                0.0,
            ),
            "facility_message": (
                "Facility information is based on the "
                "MediSathi local reference dataset."
            ),
            "data_source": (
                "MediSathi local dataset"
            ),
            "data_as_of": date.today().isoformat(),
        }

    # ========================================================
    # LOAD LOCAL FACILITY DATASET
    # ========================================================

    def _load_local_facilities(
        self,
    ) -> list[dict]:

        try:

            with open(
                FACILITIES_FILE,
                "r",
                encoding="utf-8",
            ) as handle:

                data = json.load(handle)

            if not isinstance(data, list):

                logger.warning(
                    "Facility dataset is not a list."
                )

                return []

            return data

        except FileNotFoundError:

            logger.warning(
                "Facility dataset missing: %s",
                FACILITIES_FILE,
            )

            return []

        except json.JSONDecodeError:

            logger.exception(
                "Unable to parse facility dataset."
            )

            return []

        except OSError:

            logger.exception(
                "Unable to read facility dataset."
            )

            return []

    # ========================================================
    # LOCATION LOOKUP
    # ========================================================

    def _lookup_facility_by_location(
        self,
        location: str,
        facilities: list[dict],
    ) -> dict:

        try:

            query = urllib.parse.urlencode(
                {
                    "q": location,
                    "format": "json",
                    "limit": 1,
                }
            )

            url = (
                f"{NOMINATIM_SEARCH_URL}?{query}"
            )

            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "MediSathi/1.0"
                },
            )

            with urllib.request.urlopen(
                request,
                timeout=8,
            ) as response:

                raw = response.read().decode(
                    "utf-8"
                )

            places = json.loads(raw)

            if places:

                display_name = (
                    places[0]
                    .get(
                        "display_name",
                        "",
                    )
                    .lower()
                )

                for facility in facilities:

                    region = facility.get(
                        "region",
                        "",
                    )

                    if (
                        region
                        and region.lower()
                        in display_name
                    ):

                        return {
                            "facility_available": True,
                            "facility_name": facility.get(
                                "name",
                                "Healthcare facility",
                            ),
                            "facility_address": facility.get(
                                "address",
                                "Address unavailable",
                            ),
                            "distance_km": facility.get(
                                "distance_km",
                                5.0,
                            ),
                            "facility_message": (
                                f"Facility information found "
                                f"for {location}."
                            ),
                            "data_source": (
                                "OpenStreetMap Nominatim "
                                "+ MediSathi local dataset"
                            ),
                            "data_as_of": (
                                date.today().isoformat()
                            ),
                        }

        except (
            HTTPError,
            URLError,
            TimeoutError,
        ) as exc:

            logger.warning(
                "Location lookup failed: %s",
                exc,
            )

            return {
                "facility_available": False,
                "facility_message": (
                    "The location lookup is temporarily "
                    "unavailable."
                ),
                "data_source": (
                    "OpenStreetMap Nominatim"
                ),
                "data_as_of": (
                    date.today().isoformat()
                ),
            }

        except Exception:

            logger.exception(
                "Unexpected location lookup error."
            )

            return {
                "facility_available": False,
                "facility_message": (
                    "The location lookup is temporarily "
                    "unavailable."
                ),
                "data_source": (
                    "OpenStreetMap Nominatim"
                ),
                "data_as_of": (
                    date.today().isoformat()
                ),
            }

        return {
            "facility_available": False,
            "facility_message": (
                "No matching healthcare facility was found "
                "for the given location."
            ),
            "data_source": (
                "MediSathi local dataset"
            ),
            "data_as_of": (
                date.today().isoformat()
            ),
        }


# ============================================================
# SERVER
# ============================================================

server = AgentServer()


def prewarm(proc: JobProcess):

    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


# ============================================================
# AGENT SESSION
# ============================================================

@server.rtc_session(
    agent_name="my-agent"
)
async def my_agent(ctx: JobContext):

    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # --------------------------------------------------------
    # GET CALLER
    # --------------------------------------------------------

    caller_metadata: dict[str, str] = {}

    try:

        participant = (
            await ctx.wait_for_participant()
        )

        caller_metadata = {
            "caller_id": participant.identity,
            "caller_name": participant.name or "",
        }

        logger.info(
            "Caller connected: id=%s name=%s",
            participant.identity,
            participant.name,
        )

    except Exception:

        logger.exception(
            "Unable to resolve caller identity."
        )

    # --------------------------------------------------------
    # LOAD MEMORY
    # --------------------------------------------------------

    memory_context = ""

    caller_id = caller_metadata.get(
        "caller_id"
    )

    caller_name = caller_metadata.get(
        "caller_name"
    )

    if caller_id:

        try:

            saved_caller = lookup_caller(
                DB_CONN,
                caller_id,
            )

            if saved_caller:

                saved_name = (
                    saved_caller.get("name")
                    or caller_name
                    or "unknown"
                )

                preferred_language = (
                    saved_caller.get(
                        "language_preference"
                    )
                    or "unknown"
                )

                saved_facts = (
                    saved_caller.get(
                        "facts",
                        {},
                    )
                    or {}
                )

                last_interaction = (
                    saved_caller.get(
                        "last_interaction"
                    )
                    or "unknown"
                )

                memory_context = (
                    f"Caller name: {saved_name}\n"
                    f"Preferred language: "
                    f"{preferred_language}\n"
                    f"Saved facts: "
                    f"{json.dumps(saved_facts, ensure_ascii=False)}\n"
                    f"Last interaction: "
                    f"{last_interaction}"
                )

                logger.info(
                    "Returning caller found: %s",
                    caller_id,
                )

            else:

                logger.info(
                    "New caller: %s",
                    caller_id,
                )

        except Exception:

            logger.exception(
                "Failed to load caller memory."
            )

    # --------------------------------------------------------
    # CREATE ASSISTANT
    # --------------------------------------------------------

    assistant = Assistant(
        memory_context=memory_context,
    )

    # --------------------------------------------------------
    # VOICE PIPELINE
    # --------------------------------------------------------

    session = AgentSession(

        stt=deepgram.STT(
            model="nova-3",
            language="multi",
        ),

        llm=google.LLM(
            model="gemini-3.5-flash-lite",
        ),

        tts=murf.TTS(
            voice="Anisha",
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(
                min_sentence_len=2
            ),
            text_pacing=True,
        ),

        turn_detection=MultilingualModel(),

        vad=ctx.proc.userdata["vad"],

        userdata=caller_metadata,

        preemptive_generation=True,
    )

    # --------------------------------------------------------
    # START SESSION
    # --------------------------------------------------------

    await session.start(
        agent=assistant,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if (
                        params.participant.kind
                        == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    )
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )

    # --------------------------------------------------------
    # CONNECT
    # --------------------------------------------------------

    await ctx.connect()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    cli.run_app(server)