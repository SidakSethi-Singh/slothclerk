import httpx
from typing import Optional, Dict, Any
from app.config import settings


class ElevenLabsClient:
    """Client for ElevenLabs Text-to-Speech API integration."""

    BASE_URL = "https://api.elevenlabs.io/v1"

    def __init__(self):
        self.api_key = settings.ELEVENLABS_API_KEY
        self.default_voice_id = settings.ELEVENLABS_VOICE_ID or "21m00Tcm4TlvDq8ikWAM"
        self.model_id = settings.ELEVENLABS_MODEL_ID or "eleven_turbo_v2_5"

    def is_configured(self) -> bool:
        """Checks if an ElevenLabs API key is configured."""
        return bool(self.api_key and self.api_key.strip() and self.api_key != "YOUR_ELEVENLABS_API_KEY")

    def build_briefing_script(self, analysis_data: Dict[str, Any]) -> str:
        """Constructs a spoken executive briefing from contract audit data."""
        filename = analysis_data.get("filename", "Contract Document")
        summary = analysis_data.get("summary", "Document analysis complete.")
        red_flags = analysis_data.get("red_flags", [])
        actions = analysis_data.get("action_checklist", [])
        dates = analysis_data.get("key_dates", [])

        script_parts = [
            f"Executive Legal Briefing for {filename}.",
            f"Summary: {summary}",
        ]

        if red_flags:
            high_flags = [rf for rf in red_flags if rf.get("severity") == "high"]
            flag_count = len(red_flags)
            script_parts.append(f"Attention: {flag_count} red flags detected, with {len(high_flags)} classified as high severity.")
            for i, rf in enumerate(red_flags[:3], 1):
                issue = rf.get("issue", "Unspecified issue")
                explanation = rf.get("risk_explanation", "")
                script_parts.append(f"Risk {i}: {issue}. {explanation}")
        else:
            script_parts.append("Good news: No high-risk red flags were flagged in this agreement.")

        if actions:
            script_parts.append("Immediate action items:")
            for act in actions[:2]:
                action_text = act.get("action", "")
                deadline = act.get("deadline", "Pending")
                script_parts.append(f"Action: {action_text}, deadline: {deadline}.")

        if dates:
            script_parts.append(f"Primary milestone: {dates[0].get('description', '')} on {dates[0].get('date', '')}.")

        script_parts.append("End of SlothClerk executive briefing.")
        return " ".join(script_parts)

    def synthesize_speech(self, text: str, voice_id: Optional[str] = None) -> bytes:
        """Calls ElevenLabs API to generate MP3 speech audio."""
        if not self.is_configured():
            raise ValueError("ElevenLabs API key is not configured.")

        target_voice = voice_id or self.default_voice_id
        url = f"{self.BASE_URL}/text-to-speech/{target_voice}"
        headers = {
            "xi-api-key": self.api_key.strip(),
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }
        payload = {
            "text": text[:4000],  # safeguard character limit
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True
            }
        }

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"ElevenLabs API error ({resp.status_code}): {resp.text}")
            return resp.content


elevenlabs_client = ElevenLabsClient()
