import json
import logging
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
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

from .call_analytics import (
    finish_call,
    init_analytics_db,
    start_call,
)
from .caller_memory import (
    init_db,
)
from .caller_memory import (
    lookup_caller as db_lookup_caller,
)
from .caller_memory import (
    save_caller as db_save_caller,
)
from .escalation import (
    create_escalation,
    init_escalation_db,
)

# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("healthaccess-agent")


# ============================================================
# PATHS / ENVIRONMENT
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env.local")
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
FACILITIES_FILE = DATA_DIR / "health_facilities.json"

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"


# ============================================================
# DATABASES
# ============================================================

DB_CONN = init_db()

ANALYTICS_CONN = init_analytics_db()

ESCALATION_CONN = init_escalation_db()


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are MediSathi, an AI-powered healthcare voice assistant.

Your role is to provide safe, simple and helpful healthcare
information through natural voice conversations.

You are NOT a doctor, nurse, pharmacist, or healthcare
professional.

You must never diagnose a medical condition or prescribe
medication.

============================================================
PERSONALITY
============================================================

Be:

- Friendly
- Calm
- Patient
- Empathetic
- Professional
- Concise
- Natural

Use short sentences suitable for voice conversations.

Do not sound robotic.

Do not repeatedly ask the same question.

============================================================
LANGUAGE
============================================================

Speak naturally in the language used by the user.

If the user speaks English:
Respond in English.

If the user speaks Hindi:
Respond naturally in Hindi.

If the user speaks Hinglish:
Respond naturally in simple Hinglish.

Do not force English when the user is speaking Hindi.

============================================================
HEALTHCARE SAFETY
============================================================

You provide educational information only.

Never:

- Diagnose the user.
- Prescribe medication.
- Recommend changing medication dosage.
- Recommend stopping prescribed medication.
- Recommend doubling a missed dose.
- Invent medication names.
- Invent medical history.
- Invent allergies.
- Invent test results.
- Invent prescriptions.

If the user asks about medication dosage, interactions,
stopping medication, or changing medication, advise them to
contact their doctor, pharmacist, or another qualified
healthcare professional.

============================================================
SYMPTOMS
============================================================

When discussing symptoms:

1. Listen carefully.
2. Ask only necessary follow-up questions.
3. Explain that symptoms can have different causes.
4. Do not present a diagnosis as fact.
5. Recommend appropriate professional care when needed.

If symptoms sound potentially serious, recommend urgent
medical attention.

============================================================
EMERGENCY WARNING SIGNS
============================================================

If the user reports potentially life-threatening symptoms such as:

- Severe difficulty breathing
- Severe chest pain
- Loss of consciousness
- Severe bleeding
- Seizure
- Severe allergic reaction
- Stroke-like symptoms
- Severe poisoning

Say clearly:

"This may require urgent medical attention. Please seek
emergency medical care immediately or contact your local
emergency service."

Do not diagnose.

============================================================
DAY 7 — HUMAN HELP / ESCALATION
============================================================

There are TWO situations where you should offer human help:

1. RED-FLAG SYMPTOMS
2. DIAGNOSIS REQUESTS

Before calling the escalation tool you MUST:

1. Tell the caller what information will be shared.
2. Explain why it will be shared.
3. Ask for explicit permission.
4. Wait for the caller's answer.

ONLY create the request if the caller clearly says YES.

If the caller says NO:

- Do NOT create the request.
- Respect the decision.
- Continue safe guidance.
- For emergency symptoms, still recommend immediate
  emergency medical care.

============================================================
ESCALATION INFORMATION
============================================================

Only send useful details:

- Who needs help
- What happened
- What the agent already checked
- Urgency
- Caller language
- Preferred follow-up method

Do NOT send the full conversation.

Never include:

- Passwords
- OTPs
- PINs
- Aadhaar numbers
- PAN numbers
- Bank information
- Card numbers
- Unnecessary private information

============================================================
ESCALATION URGENCY
============================================================

Use:

"emergency"
for potentially life-threatening red-flag symptoms.

Use:

"high"
for serious situations needing prompt human review.

Use:

"medium"
for non-emergency human assistance.

Use:

"low"
for non-urgent human assistance.

============================================================
AFTER ESCALATION
============================================================

When the escalation tool successfully creates a request:

Tell the caller:

1. The request was created.
2. Their reference ID.
3. The request is currently open.
4. What will happen next.

Do NOT promise an immediate human response unless you know
that a human is immediately available.

============================================================
NORMAL CONVERSATIONS
============================================================

Do NOT create a human-help request for ordinary symptoms.

For example:

- Mild headache
- Common cold
- Mild cough
- General health questions

These should normally receive safe educational guidance.

============================================================
DAY 5 HEALTH TOOL
============================================================

You have access to a healthcare tool that can:

1. Assess general urgency based on symptoms.
2. Look up healthcare facility information.

Use the tool when the user needs practical healthcare
guidance or asks for a nearby healthcare facility.

The tool provides general triage information.

It does NOT provide a medical diagnosis.

============================================================
CALLER MEMORY
============================================================

Caller memory may contain:

- Name
- Preferred language
- Previously saved safe facts
- Previous interaction information

Use memory only when relevant.

Never invent information that is not present in memory.

Never expose private or unnecessary information.

Never ask for:

- Aadhaar number
- PAN number
- OTP
- Passwords
- Bank details
- Credit card information

============================================================
MEDICATION REMINDERS
============================================================

If this is an outbound medication reminder call:

Clearly explain:

1. Who you are.
2. Why you are calling.
3. That the user can opt out of future reminder calls.

Then ask:

"Have you taken your scheduled medicine?"

If the user confirms that they took it:

"Great, thank you for confirming. Please continue following
the medication schedule provided by your healthcare professional.
Take care."

If the user has not taken it or forgot:

"Okay, that's understandable. Please follow the medication
instructions provided with your prescription. If you're unsure
what to do after missing a dose, please contact your doctor
or pharmacist."

Never recommend doubling a dose.

============================================================
OPT-OUT
============================================================

If the user says:

- Don't call me again.
- Stop calling me.
- Remove me.
- I don't want reminders.
- Please don't call.
- No more calls.

Respect the request immediately.

============================================================
IDENTITY
============================================================

If asked who you are:

"I'm MediSathi, an AI healthcare assistant."

If asked whether you are a doctor:

"No. I'm an AI healthcare assistant. I can provide general
health information, but I'm not a doctor and I can't replace
professional medical advice."

============================================================
DAY 8 — CALL SUCCESS
============================================================

A call should be considered successful when:

- The caller receives meaningful safe healthcare guidance, OR
- A human-help escalation is successfully created.

Do not expose analytics information to the caller.

============================================================
DAY 9 — SPECIALIST HANDOFF
============================================================

You have access to a clinic and appointment specialist for
specific healthcare facility and appointment-related requests.

Transfer to the specialist ONLY if the user specifically needs:

- Help finding a clinic or healthcare facility
- Help choosing between healthcare facilities
- Clinic location or facility information
- Appointment-related assistance
- Help deciding where to seek or book an appointment

DO NOT transfer for:

- General health questions
- Symptom questions or assessment
- Medication-related questions
- Health education requests
- Triage or emergency guidance
- Diagnosis requests
- Human help escalation (use the human help tool instead)

If the user's request requires specialist help:

1. Clearly tell the user: "I'll connect you to our Clinic and
Appointment Specialist."
2. Use the transfer_to_clinic_specialist tool.
3. Wait for the tool to complete successfully.

Before transferring, ensure the user explicitly needs clinic or
appointment help, not general healthcare guidance.

============================================================
FINAL RULE
============================================================

Always prioritize safety.

If you are unsure, do not guess.

Recommend contacting an appropriate healthcare professional.
"""


# ============================================================
# CLINIC APPOINTMENT SPECIALIST PROMPT
# ============================================================

CLINIC_SPECIALIST_PROMPT = """
You are the HealthAccess Clinic and Appointment Specialist.

Your only responsibility is helping users with clinics,
healthcare facilities, and appointments.

You speak in a professional male voice (Arjun).

============================================================
YOUR ROLE
============================================================

You help users:

1. Find suitable clinics or healthcare facilities.
2. Understand clinic and facility options.
3. Choose a facility based on location and specialty.
4. Get information about healthcare services.
5. Arrange or understand appointment processes.
6. Understand facility hours and location.

============================================================
WHAT YOU ARE NOT
============================================================

You are NOT a doctor or healthcare professional.

You must NEVER:

- Diagnose medical conditions.
- Prescribe medication.
- Provide definitive medical treatment.
- Replace professional medical advice.
- Give clinical recommendations.
- Assess symptoms.

If the user needs medical advice, symptom assessment, or
health guidance, tell them clearly:

"This question is about general health guidance. Let me help
by connecting you with the right resources."

============================================================
PERSONALITY
============================================================

Be:

- Friendly and approachable
- Calm and patient
- Professional and helpful
- Concise and clear
- Natural in conversation

============================================================
LANGUAGE
============================================================

Speak naturally in the language the user is using.

If they speak English: Respond in English.
If they speak Hindi: Respond naturally in Hindi.
If they speak Hinglish: Respond in Hinglish.

============================================================
IMPORTANT RULES
============================================================

1. Do NOT ask the user to repeat their original request.
2. Do NOT ask questions like "What was your question?"
3. Do NOT ask "Can you explain everything again?"
4. The user has already told me their request.
5. Continue helping from where they left off.
6. Only ask for missing information.
7. Be empathetic to their healthcare access concerns.

============================================================
IF USER ASKS MEDICAL QUESTIONS
============================================================

If the user asks about symptoms, diagnosis, or medical advice:

Do NOT answer medical questions.

Instead, gently guide them back:

"That sounds like a medical question. I'm focused on helping
with clinics and appointments. For health guidance, please ask
MediSathi directly."

============================================================
EXAMPLE SCENARIO
============================================================

User (to HealthAccess): "I need to find a clinic for a
general checkup near me."

HealthAccess: "I'll connect you to our Clinic and Appointment
Specialist."

[Handoff occurs, I take over]

Me (Specialist): "Hello, I'm the Clinic and Appointment
Specialist. I already know you need a clinic for a general
checkup. Which city or area are you in?"

User: "Bengaluru."

Me: "Great! I can help you find a clinic in Bengaluru.
Are there any specific preferences, like a nearby area?"

[Continue assisting]

============================================================
CALLER MEMORY
============================================================

Use saved caller information when relevant.

Never invent information.

Use only what was shared in the conversation.

============================================================
FINAL RULE
============================================================

Always prioritize the user's needs.

Focus on finding the right healthcare facility.

Be helpful, professional, and caring.
"""


# ============================================================
# CLINIC APPOINTMENT AGENT
# ============================================================


class ClinicAppointmentAgent(Agent):
    """
    Specialist agent for clinic and appointment-related requests.

    This agent handles:
    - Finding healthcare facilities
    - Helping users choose clinics
    - Providing facility information
    - Appointment assistance

    It does NOT handle medical diagnosis or health advice.
    """

    def __init__(
        self,
        memory_context: str = "",
        voice_name: str = "Arjun",
    ) -> None:

        self.voice_name = voice_name

        instructions = CLINIC_SPECIALIST_PROMPT

        if memory_context:
            instructions += f"""

============================================================
CURRENT CALLER MEMORY
============================================================

Use the following saved caller information only when relevant.

Do not invent additional information.

{memory_context}

============================================================
END CALLER MEMORY
============================================================
"""

        super().__init__(instructions=instructions)

    # ========================================================
    # FACILITY LOOKUP
    # ========================================================

    def _load_local_facilities(self) -> list[dict]:
        """Load healthcare facility dataset."""

        try:
            with open(
                FACILITIES_FILE,
                encoding="utf-8",
            ) as handle:
                data = json.load(handle)

        except FileNotFoundError:
            logger.warning(
                "Facility dataset not found: %s",
                FACILITIES_FILE,
            )
            return []

        except json.JSONDecodeError:
            logger.exception("Facility dataset contains invalid JSON.")
            return []

        except OSError:
            logger.exception("Unable to read facility dataset.")
            return []

        if not isinstance(data, list):
            logger.warning("Facility dataset must contain a JSON list.")
            return []

        return [item for item in data if isinstance(item, dict)]

    def _lookup_facility_by_location(
        self,
        location: str,
        facilities: list[dict],
    ) -> dict:
        """Find healthcare facility by location."""

        try:
            query = urllib.parse.urlencode(
                {
                    "q": location,
                    "format": "json",
                    "limit": 1,
                }
            )

            url = f"{NOMINATIM_SEARCH_URL}?{query}"

            request = urllib.request.Request(
                url,
                headers={"User-Agent": "MediSathi/1.0"},
            )

            with urllib.request.urlopen(
                request,
                timeout=8,
            ) as response:
                raw_response = response.read().decode("utf-8")

            places = json.loads(raw_response)

            if not isinstance(places, list) or not places:
                return {
                    "facility_available": False,
                    "facility_message": ("No location information was found."),
                    "data_source": ("OpenStreetMap Nominatim"),
                    "data_as_of": (date.today().isoformat()),
                }

            display_name = places[0].get("display_name", "").lower()

            for facility in facilities:
                region = str(facility.get("region", "")).strip()

                if not region:
                    continue

                if region.lower() in display_name:
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
                            f"Facility information found for {location}."
                        ),
                        "data_source": (
                            "OpenStreetMap Nominatim + HealthAccess local dataset"
                        ),
                        "data_as_of": (date.today().isoformat()),
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
                "facility_message": ("The location lookup is temporarily unavailable."),
                "data_source": ("OpenStreetMap Nominatim"),
                "data_as_of": (date.today().isoformat()),
            }

        except json.JSONDecodeError:
            logger.exception("Invalid response from location service.")

            return {
                "facility_available": False,
                "facility_message": ("The location service returned invalid data."),
                "data_source": ("OpenStreetMap Nominatim"),
                "data_as_of": (date.today().isoformat()),
            }

        except Exception:
            logger.exception("Unexpected location lookup error.")

            return {
                "facility_available": False,
                "facility_message": ("The location lookup is temporarily unavailable."),
                "data_source": ("OpenStreetMap Nominatim"),
                "data_as_of": (date.today().isoformat()),
            }

        return {
            "facility_available": False,
            "facility_message": (
                "No matching healthcare facility was found for the given location."
            ),
            "data_source": ("HealthAccess local dataset"),
            "data_as_of": (date.today().isoformat()),
        }

    @function_tool
    async def find_healthcare_facility(
        self,
        context: RunContext,
        location: str | None = None,
    ):
        """Find healthcare facilities by location."""

        del context

        logger.info(
            "CLINIC SPECIALIST | find_healthcare_facility | location=%s",
            location,
        )

        facilities = self._load_local_facilities()

        if not facilities:
            return {
                "success": False,
                "error": "no_facilities_available",
                "message": ("No healthcare facility data is currently available."),
            }

        if location and location.strip():
            location_result = self._lookup_facility_by_location(
                location.strip(),
                facilities,
            )

            if location_result.get("facility_available"):
                return {
                    "success": True,
                    **location_result,
                }

        default_facility = facilities[0]

        return {
            "success": True,
            "facility_available": True,
            "facility_name": default_facility.get(
                "name",
                "Healthcare facility",
            ),
            "facility_address": default_facility.get(
                "address",
                "Address unavailable",
            ),
            "distance_km": default_facility.get(
                "distance_km",
                0.0,
            ),
            "facility_message": (
                "Facility information is based on the "
                "HealthAccess local reference dataset."
            ),
            "data_source": ("HealthAccess local dataset"),
            "data_as_of": (date.today().isoformat()),
        }


# ============================================================
# ASSISTANT
# ============================================================


class Assistant(Agent):
    def __init__(
        self,
        memory_context: str = "",
    ) -> None:

        instructions = SYSTEM_PROMPT

        if memory_context:
            instructions += f"""

============================================================
CURRENT CALLER MEMORY
============================================================

Use the following saved caller information only when relevant.

Do not invent additional information.

{memory_context}

============================================================
END CALLER MEMORY
============================================================
"""

        super().__init__(instructions=instructions)

    # ========================================================
    # CALLER MEMORY TOOL
    # ========================================================

    @function_tool
    async def lookup_caller(
        self,
        context: RunContext,
        user_id: str | None = None,
    ):
        """Look up saved caller information."""

        if not user_id:
            try:
                userdata = context.userdata
            except Exception:
                userdata = None

            if isinstance(userdata, dict):
                user_id = userdata.get("caller_id")

        if not user_id:
            return {
                "found": False,
                "reason": "missing_user_id",
            }

        try:
            record = db_lookup_caller(
                DB_CONN,
                user_id,
            )

        except Exception:
            logger.exception("Caller lookup failed.")

            return {
                "found": False,
                "reason": "database_error",
            }

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
    # SAVE CALLER TOOL
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
        """Save safe caller information."""

        if not user_id:
            try:
                userdata = context.userdata
            except Exception:
                userdata = None

            if isinstance(userdata, dict):
                user_id = userdata.get("caller_id")

        if not user_id:
            return {
                "saved": False,
                "reason": "missing_user_id",
            }

        try:
            record = db_save_caller(
                DB_CONN,
                user_id=user_id,
                name=name,
                language_preference=language_preference,
                facts=facts,
            )

            logger.info(
                "Caller memory saved: %s",
                user_id,
            )

            return {
                "saved": True,
                **record,
            }

        except Exception:
            logger.exception("Caller memory save failed.")

            return {
                "saved": False,
                "reason": "database_error",
            }

    # ========================================================
    # DAY 7 HUMAN HELP TOOL
    # ========================================================

    @function_tool
    async def create_human_help_request(
        self,
        context: RunContext,
        issue_type: str,
        summary: str,
        agent_checked: str,
        urgency: str,
        language: str,
        preferred_follow_up: str,
        permission_confirmed: bool = False,
    ):
        """Create a human-help request only after permission."""

        if permission_confirmed is not True:
            logger.warning("Escalation blocked: caller permission missing.")

            return {
                "success": False,
                "created": False,
                "reason": "caller_permission_required",
                "message": (
                    "Explicit caller permission is required "
                    "before creating a human-help request."
                ),
            }

        caller_id = ""
        caller_name = ""

        try:
            userdata = context.userdata

            if isinstance(userdata, dict):
                caller_id = userdata.get("caller_id") or ""

                caller_name = userdata.get("caller_name") or ""

        except Exception:
            logger.exception("Unable to read caller information.")

        if not issue_type.strip():
            return {
                "success": False,
                "created": False,
                "reason": "missing_issue_type",
            }

        if not summary.strip():
            return {
                "success": False,
                "created": False,
                "reason": "missing_summary",
            }

        if not agent_checked.strip():
            return {
                "success": False,
                "created": False,
                "reason": "missing_agent_checked",
            }

        try:
            result = create_escalation(
                ESCALATION_CONN,
                caller_id=caller_id,
                caller_name=caller_name,
                issue_type=issue_type,
                summary=summary,
                agent_checked=agent_checked,
                urgency=urgency,
                language=language,
                preferred_follow_up=preferred_follow_up,
            )

            logger.info(
                "HUMAN ESCALATION CREATED | reference=%s | urgency=%s",
                result.get("reference_id"),
                result.get("urgency"),
            )

            return result

        except Exception:
            logger.exception("Failed to create human-help request.")

            return {
                "success": False,
                "created": False,
                "reason": "database_error",
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
        """Assess general urgency and find facility information."""

        del context

        logger.info(
            "HEALTH TOOL | symptoms=%s | location=%s",
            symptoms,
            location,
        )

        if not symptoms or not symptoms.strip():
            return {
                "success": False,
                "error": "missing_symptoms",
                "message": "Symptoms are required.",
            }

        try:
            symptoms_clean = symptoms.strip()
            symptoms_lower = symptoms_clean.lower()

            triage_level, triage_reason = self._determine_triage(symptoms_lower)

            facility_result = self._lookup_nearest_facility(location)

            result = {
                "success": True,
                "symptoms": symptoms_clean,
                "location": location,
                "triage_level": triage_level,
                "triage_reason": triage_reason,
                "data_source": facility_result.get(
                    "data_source",
                    "HealthAccess local dataset",
                ),
                "data_as_of": facility_result.get(
                    "data_as_of",
                    date.today().isoformat(),
                ),
            }

            result.update(facility_result)

            logger.info(
                "HEALTH TOOL RESULT | %s",
                result,
            )

            return result

        except Exception:
            logger.exception("Health tool failed.")

            return {
                "success": False,
                "error": "health_data_unavailable",
                "message": (
                    "The HealthAccess health information "
                    "source is temporarily unavailable."
                ),
                "data_source": ("HealthAccess local dataset"),
                "data_as_of": (date.today().isoformat()),
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

        for keyword in emergency_keywords:
            if keyword in symptoms:
                return (
                    "Emergency care",
                    (
                        "The symptoms include serious warning "
                        "signs that may need immediate "
                        "medical attention."
                    ),
                )

        for keyword in prompt_keywords:
            if keyword in symptoms:
                return (
                    "Prompt medical consultation",
                    (
                        "These symptoms may require a prompt "
                        "consultation with a healthcare "
                        "professional."
                    ),
                )

        if "fever" in symptoms and "cough" in symptoms:
            return (
                "Prompt medical consultation",
                (
                    "Fever combined with respiratory symptoms "
                    "may need prompt medical attention."
                ),
            )

        for keyword in routine_keywords:
            if keyword in symptoms:
                return (
                    "Routine healthcare consultation",
                    (
                        "The symptoms may be suitable for "
                        "routine healthcare guidance, but "
                        "professional care is recommended if "
                        "they persist or worsen."
                    ),
                )

        return (
            "Routine healthcare consultation",
            (
                "Based on the symptoms described, consider "
                "speaking with a healthcare professional if "
                "the problem continues, worsens, or causes "
                "concern."
            ),
        )

    # ========================================================
    # FACILITY LOOKUP
    # ========================================================

    def _lookup_nearest_facility(
        self,
        location: str | None,
    ) -> dict:

        facilities = self._load_local_facilities()

        if not facilities:
            return {
                "facility_available": False,
                "facility_message": ("No local healthcare facility data is available."),
                "data_source": ("HealthAccess local dataset"),
                "data_as_of": (date.today().isoformat()),
            }

        if location and location.strip():
            location_result = self._lookup_facility_by_location(
                location.strip(),
                facilities,
            )

            if location_result.get("facility_available"):
                return location_result

        default_facility = facilities[0]

        return {
            "facility_available": True,
            "facility_name": default_facility.get(
                "name",
                "Healthcare facility",
            ),
            "facility_address": default_facility.get(
                "address",
                "Address unavailable",
            ),
            "distance_km": default_facility.get(
                "distance_km",
                0.0,
            ),
            "facility_message": (
                "Facility information is based on the "
                "HealthAccess local reference dataset."
            ),
            "data_source": ("HealthAccess local dataset"),
            "data_as_of": (date.today().isoformat()),
        }

    # ========================================================
    # LOAD FACILITY DATASET
    # ========================================================

    def _load_local_facilities(self) -> list[dict]:

        try:
            with open(
                FACILITIES_FILE,
                encoding="utf-8",
            ) as handle:
                data = json.load(handle)

        except FileNotFoundError:
            logger.warning(
                "Facility dataset not found: %s",
                FACILITIES_FILE,
            )
            return []

        except json.JSONDecodeError:
            logger.exception("Facility dataset contains invalid JSON.")
            return []

        except OSError:
            logger.exception("Unable to read facility dataset.")
            return []

        if not isinstance(data, list):
            logger.warning("Facility dataset must contain a JSON list.")
            return []

        return [item for item in data if isinstance(item, dict)]

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

            url = f"{NOMINATIM_SEARCH_URL}?{query}"

            request = urllib.request.Request(
                url,
                headers={"User-Agent": "MediSathi/1.0"},
            )

            with urllib.request.urlopen(
                request,
                timeout=8,
            ) as response:
                raw_response = response.read().decode("utf-8")

            places = json.loads(raw_response)

            if not isinstance(places, list) or not places:
                return {
                    "facility_available": False,
                    "facility_message": ("No location information was found."),
                    "data_source": ("OpenStreetMap Nominatim"),
                    "data_as_of": (date.today().isoformat()),
                }

            display_name = places[0].get("display_name", "").lower()

            for facility in facilities:
                region = str(facility.get("region", "")).strip()

                if not region:
                    continue

                if region.lower() in display_name:
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
                            f"Facility information found for {location}."
                        ),
                        "data_source": (
                            "OpenStreetMap Nominatim + HealthAccess local dataset"
                        ),
                        "data_as_of": (date.today().isoformat()),
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
                "facility_message": ("The location lookup is temporarily unavailable."),
                "data_source": ("OpenStreetMap Nominatim"),
                "data_as_of": (date.today().isoformat()),
            }

        except json.JSONDecodeError:
            logger.exception("Invalid response from location service.")

            return {
                "facility_available": False,
                "facility_message": ("The location service returned invalid data."),
                "data_source": ("OpenStreetMap Nominatim"),
                "data_as_of": (date.today().isoformat()),
            }

        except Exception:
            logger.exception("Unexpected location lookup error.")

            return {
                "facility_available": False,
                "facility_message": ("The location lookup is temporarily unavailable."),
                "data_source": ("OpenStreetMap Nominatim"),
                "data_as_of": (date.today().isoformat()),
            }

        return {
            "facility_available": False,
            "facility_message": (
                "No matching healthcare facility was found for the given location."
            ),
            "data_source": ("HealthAccess local dataset"),
            "data_as_of": (date.today().isoformat()),
        }

    # ========================================================
    # DAY 9 SPECIALIST HANDOFF
    # ========================================================

    @function_tool
    async def transfer_to_clinic_specialist(
        self,
        context: RunContext,
    ):
        """
        Transfer the user to the Clinic and Appointment Specialist.

        Use this tool ONLY when the user explicitly needs:
        - Help finding a clinic or healthcare facility
        - Help choosing between healthcare facilities
        - Clinic information or location details
        - Appointment-related assistance

        DO NOT use for general health questions, symptom assessment,
        medication questions, or medical advice.
        """

        caller_id = ""
        caller_name = ""

        try:
            userdata = context.userdata

            if isinstance(userdata, dict):
                caller_id = userdata.get("caller_id") or ""

                caller_name = userdata.get("caller_name") or ""

        except Exception:
            logger.exception(
                "Unable to read caller information for specialist handoff."
            )

        # Get memory context for specialist
        memory_context = ""

        if caller_id:
            try:
                saved_caller = db_lookup_caller(
                    DB_CONN,
                    caller_id,
                )

                if saved_caller:
                    saved_name = saved_caller.get("name") or caller_name or "unknown"

                    preferred_language = (
                        saved_caller.get("language_preference") or "unknown"
                    )

                    saved_facts = (
                        saved_caller.get(
                            "facts",
                            {},
                        )
                        or {}
                    )

                    memory_context = (
                        f"Caller name: {saved_name}\n"
                        f"Preferred language: "
                        f"{preferred_language}\n"
                        f"Saved facts: "
                        f"{json.dumps(saved_facts, ensure_ascii=False)}"
                    )

            except Exception:
                logger.exception("Failed to load caller memory for specialist.")

        # Switch agent to specialist mode
        try:
            # Create specialist agent with Arjun male voice
            specialist = ClinicAppointmentAgent(
                memory_context=memory_context,
                voice_name="Arjun",
            )

            logger.info(
                "DAY 9 SPECIALIST HANDOFF | ClinicAppointmentAgent created | caller=%s | voice=Arjun",
                caller_id,
            )

            # Record analytics event for handoff
            try:
                # Record handoff event using analytics
                ANALYTICS_CONN.execute(
                    """
                    INSERT INTO calls (
                        call_id,
                        timestamp,
                        channel,
                        successful,
                        status
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        f"{caller_id}_specialist",
                        datetime.now(timezone.utc).isoformat(),
                        "voice",
                        0,
                        "specialist_handoff",
                    ),
                )

                ANALYTICS_CONN.commit()

                logger.info("DAY 9 ANALYTICS | Specialist handoff event recorded")

            except Exception:
                logger.exception("Failed to record specialist handoff analytics")

            # Tell LLM to switch to specialist instructions
            # by returning the specialist's prompt for context
            return {
                "success": True,
                "specialist_ready": True,
                "specialist_type": ("ClinicAppointmentAgent"),
                "action": "use_specialist_instructions",
                "message": (
                    "Specialist agent ready. You are now "
                    "operating as the Clinic and Appointment "
                    "Specialist. Greet the user and proceed with "
                    "finding clinics and facilities."
                ),
            }

        except Exception:
            logger.exception(
                "DAY 9 SPECIALIST HANDOFF | FAILED TO CREATE SPECIALIST AGENT"
            )

            return {
                "success": False,
                "specialist_ready": False,
                "error": "specialist_unavailable",
                "message": (
                    "I'm unable to connect you to the clinic "
                    "specialist right now, but I can still help "
                    "you. What clinic or healthcare facility "
                    "are you looking for?"
                ),
            }


# ============================================================
# LIVEKIT SERVER
# ============================================================

server = AgentServer()


# ============================================================
# PREWARM
# ============================================================


def prewarm(proc: JobProcess):

    proc.userdata["vad"] = silero.VAD.load()

    logger.info("VAD prewarmed successfully.")


server.setup_fnc = prewarm


# ============================================================
# LIVEKIT SESSION
# ============================================================


@server.rtc_session(agent_name="my-agent")
async def my_agent(
    ctx: JobContext,
):

    ctx.log_context_fields = {"room": ctx.room.name}

    logger.info("==================================================")

    logger.info(
        "LIVEKIT SESSION STARTED | room=%s",
        ctx.room.name,
    )

    logger.info("==================================================")

    # ========================================================
    # JOB METADATA
    # ========================================================

    dial_info: dict = {}

    try:
        raw_metadata = ctx.job.metadata or ""

        if raw_metadata.strip():
            parsed_metadata = json.loads(raw_metadata)

            if isinstance(
                parsed_metadata,
                dict,
            ):
                dial_info = parsed_metadata

    except json.JSONDecodeError:
        logger.warning(
            "Invalid job metadata: %s",
            ctx.job.metadata,
        )

    # ========================================================
    # OUTBOUND CALL
    # ========================================================

    phone_number = dial_info.get("phone_number")

    is_outbound = bool(phone_number)

    # ========================================================
    # DAY 8 ANALYTICS
    # ========================================================

    analytics_call_id = ctx.room.name

    call_channel = "sip" if is_outbound else "browser"

    logger.info(
        "DAY 8 ANALYTICS | Preparing call | id=%s | channel=%s",
        analytics_call_id,
        call_channel,
    )

    # ========================================================
    # CONNECT TO ROOM
    # ========================================================

    await ctx.connect()

    # --------------------------------------------------------
    # START CALL RECORD AFTER ROOM IS LIVE
    # --------------------------------------------------------

    try:
        start_call(
            ANALYTICS_CONN,
            call_id=analytics_call_id,
            channel=call_channel,
        )

        logger.info(
            "DAY 8 ANALYTICS | CALL STARTED | "
            "id=%s | channel=%s | status=active | successful=0",
            analytics_call_id,
            call_channel,
        )

    except Exception:
        logger.exception("DAY 8 ANALYTICS | FAILED TO RECORD CALL START")

    logger.info(
        "Connected to LiveKit room: %s",
        ctx.room.name,
    )

    # ========================================================
    # FIND PARTICIPANT
    # ========================================================

    caller_metadata: dict[str, str] = {}

    try:
        if is_outbound:
            participant = await ctx.wait_for_participant(
                kind=(rtc.ParticipantKind.PARTICIPANT_KIND_SIP)
            )

        else:
            participant = await ctx.wait_for_participant()

        caller_metadata = {
            "caller_id": participant.identity,
            "caller_name": participant.name or "",
        }

        logger.info(
            "Caller connected | id=%s | name=%s",
            participant.identity,
            participant.name,
        )

    except Exception:
        logger.exception("Unable to resolve caller identity.")

    # ========================================================
    # CALLER MEMORY
    # ========================================================

    memory_context = ""

    caller_id = caller_metadata.get("caller_id")

    caller_name = caller_metadata.get("caller_name")

    if caller_id:
        try:
            saved_caller = db_lookup_caller(
                DB_CONN,
                caller_id,
            )

            if saved_caller:
                saved_name = saved_caller.get("name") or caller_name or "unknown"

                preferred_language = (
                    saved_caller.get("language_preference") or "unknown"
                )

                saved_facts = (
                    saved_caller.get(
                        "facts",
                        {},
                    )
                    or {}
                )

                last_interaction = saved_caller.get("last_interaction") or "unknown"

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
            logger.exception("Failed to load caller memory.")

    # ========================================================
    # CREATE ASSISTANT
    # ========================================================

    assistant = Assistant(memory_context=memory_context)

    # ========================================================
    # AGENT SESSION
    # ========================================================

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
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=1),
            text_pacing=False,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        userdata=caller_metadata,
        preemptive_generation=True,
    )

    # ========================================================
    # START AGENT SESSION
    # ========================================================

    await session.start(
        agent=assistant,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=(
                room_io.AudioInputOptions(
                    noise_cancellation=lambda params: (
                        noise_cancellation.BVCTelephony()
                        if (
                            params.participant.kind
                            == (rtc.ParticipantKind.PARTICIPANT_KIND_SIP)
                        )
                        else noise_cancellation.BVC()
                    ),
                )
            ),
        ),
    )

    logger.info("Agent session started successfully.")

    # ========================================================
    # DAY 8 ANALYTICS — FINISH CALL
    # ========================================================

    async def record_call_outcome():

        logger.info(
            "DAY 8 ANALYTICS | Shutdown callback triggered | id=%s",
            analytics_call_id,
        )

        try:
            finish_call(
                ANALYTICS_CONN,
                call_id=analytics_call_id,
                successful=True,
            )

            logger.info(
                "DAY 8 ANALYTICS | CALL FINISHED | id=%s | successful=True",
                analytics_call_id,
            )

        except Exception:
            logger.exception("DAY 8 ANALYTICS | FAILED TO RECORD CALL OUTCOME")

    ctx.add_shutdown_callback(record_call_outcome)

    # ========================================================
    # OUTBOUND CALL GREETING
    # ========================================================

    if is_outbound:
        await session.generate_reply(
            instructions=(
                "Start the outbound medication reminder "
                "call now. Clearly introduce MediSathi, "
                "explain that this is a scheduled medication "
                "reminder, tell the user they can opt out "
                "of future reminder calls, and then ask "
                "whether they have taken their scheduled "
                "medicine. Keep the opening short and natural."
            )
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    cli.run_app(server)
