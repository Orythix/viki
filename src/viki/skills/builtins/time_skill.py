from datetime import datetime
from typing import Any

from viki.skills.base import BaseSkill

# Fuzzy location -> IANA timezone name mapping for common queries
_LOCATION_TZ_MAP = {
    # Europe
    "sweden": "Europe/Stockholm",
    "stockholm": "Europe/Stockholm",
    "norway": "Europe/Oslo",
    "oslo": "Europe/Oslo",
    "denmark": "Europe/Copenhagen",
    "copenhagen": "Europe/Copenhagen",
    "finland": "Europe/Helsinki",
    "helsinki": "Europe/Helsinki",
    "uk": "Europe/London",
    "london": "Europe/London",
    "england": "Europe/London",
    "britain": "Europe/London",
    "france": "Europe/Paris",
    "paris": "Europe/Paris",
    "germany": "Europe/Berlin",
    "berlin": "Europe/Berlin",
    "spain": "Europe/Madrid",
    "madrid": "Europe/Madrid",
    "italy": "Europe/Rome",
    "rome": "Europe/Rome",
    "netherlands": "Europe/Amsterdam",
    "amsterdam": "Europe/Amsterdam",
    "switzerland": "Europe/Zurich",
    "zurich": "Europe/Zurich",
    "austria": "Europe/Vienna",
    "vienna": "Europe/Vienna",
    "portugal": "Europe/Lisbon",
    "lisbon": "Europe/Lisbon",
    "poland": "Europe/Warsaw",
    "warsaw": "Europe/Warsaw",
    "russia": "Europe/Moscow",
    "moscow": "Europe/Moscow",
    "ukraine": "Europe/Kyiv",
    "kyiv": "Europe/Kyiv",
    "greece": "Europe/Athens",
    "athens": "Europe/Athens",
    "turkey": "Europe/Istanbul",
    "istanbul": "Europe/Istanbul",
    # Americas
    "new york": "America/New_York",
    "nyc": "America/New_York",
    "eastern": "America/New_York",
    "est": "America/New_York",
    "chicago": "America/Chicago",
    "central": "America/Chicago",
    "denver": "America/Denver",
    "mountain": "America/Denver",
    "los angeles": "America/Los_Angeles",
    "la": "America/Los_Angeles",
    "pacific": "America/Los_Angeles",
    "pst": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "canada": "America/Toronto",
    "toronto": "America/Toronto",
    "vancouver": "America/Vancouver",
    "mexico": "America/Mexico_City",
    "mexico city": "America/Mexico_City",
    "brazil": "America/Sao_Paulo",
    "sao paulo": "America/Sao_Paulo",
    "argentina": "America/Argentina/Buenos_Aires",
    "buenos aires": "America/Argentina/Buenos_Aires",
    # Asia-Pacific
    "india": "Asia/Kolkata",
    "ist": "Asia/Kolkata",
    "kolkata": "Asia/Kolkata",
    "mumbai": "Asia/Kolkata",
    "delhi": "Asia/Kolkata",
    "china": "Asia/Shanghai",
    "beijing": "Asia/Shanghai",
    "shanghai": "Asia/Shanghai",
    "japan": "Asia/Tokyo",
    "tokyo": "Asia/Tokyo",
    "korea": "Asia/Seoul",
    "seoul": "Asia/Seoul",
    "singapore": "Asia/Singapore",
    "hong kong": "Asia/Hong_Kong",
    "dubai": "Asia/Dubai",
    "uae": "Asia/Dubai",
    "saudi arabia": "Asia/Riyadh",
    "riyadh": "Asia/Riyadh",
    "pakistan": "Asia/Karachi",
    "karachi": "Asia/Karachi",
    "bangladesh": "Asia/Dhaka",
    "dhaka": "Asia/Dhaka",
    "thailand": "Asia/Bangkok",
    "bangkok": "Asia/Bangkok",
    "indonesia": "Asia/Jakarta",
    "jakarta": "Asia/Jakarta",
    "philippines": "Asia/Manila",
    "manila": "Asia/Manila",
    "australia": "Australia/Sydney",
    "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "perth": "Australia/Perth",
    # Africa
    "egypt": "Africa/Cairo",
    "cairo": "Africa/Cairo",
    "nigeria": "Africa/Lagos",
    "lagos": "Africa/Lagos",
    "south africa": "Africa/Johannesburg",
    "johannesburg": "Africa/Johannesburg",
    "kenya": "Africa/Nairobi",
    "nairobi": "Africa/Nairobi",
    # UTC
    "utc": "UTC",
    "gmt": "UTC",
}


class TimeSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "time_skill"

    @property
    def description(self) -> str:
        return (
            "Returns the current time and date. "
            "Accepts an optional 'location' or 'timezone' parameter to get time in any city or country. "
            'Examples: {"location": "Sweden"}, {"timezone": "America/New_York"}, {} for local time.'
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City or country name, e.g. 'Sweden', 'Tokyo', 'New York'",
                },
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone string, e.g. 'Europe/Stockholm', 'America/New_York'",
                },
            },
        }

    async def execute(self, params: dict[str, Any] = None) -> str:
        params = params or {}
        location = (params.get("location") or "").strip()
        tz_name = (params.get("timezone") or "").strip()

        # Resolve location to a timezone name
        if location and not tz_name:
            tz_name = _LOCATION_TZ_MAP.get(location.lower())
            if not tz_name:
                # Try partial match
                for key, val in _LOCATION_TZ_MAP.items():
                    if key in location.lower() or location.lower() in key:
                        tz_name = val
                        break

        if tz_name:
            try:
                from zoneinfo import ZoneInfo

                tz = ZoneInfo(tz_name)
                now = datetime.now(tz)
                label = location or tz_name
                # Format: "Thursday, 14 May 2026, 07:25:31 CEST (UTC+2)"
                offset = now.strftime("%z")
                offset_fmt = f"UTC{offset[:3]}:{offset[3:]}" if len(offset) == 5 else "UTC"
                tz_abbr = now.strftime("%Z")
                return (
                    f"Current time in {label.title()}: "
                    f"{now.strftime('%A, %d %B %Y, %H:%M:%S')} {tz_abbr} ({offset_fmt})"
                )
            except Exception as e:
                return f"Could not determine time for '{location or tz_name}': {e}"

        # No location — return local system time
        now = datetime.now()
        return f"Local time: {now.strftime('%A, %d %B %Y, %H:%M:%S')}"
