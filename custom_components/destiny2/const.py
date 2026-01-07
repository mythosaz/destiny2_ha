"""Constants for the Destiny 2 integration."""
from datetime import timedelta

DOMAIN = "destiny2"

# Configuration
CONF_API_KEY = "api_key"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"

# Bungie API endpoints
OAUTH_AUTHORIZE_URL = "https://www.bungie.net/en/OAuth/Authorize"
OAUTH_TOKEN_URL = "https://www.bungie.net/Platform/App/OAuth/Token/"
API_BASE_URL = "https://www.bungie.net/Platform"

# API paths
API_MILESTONES = "/Destiny2/Milestones/"
API_PROFILE = "/Destiny2/{membershipType}/Profile/{destinyMembershipId}/"

# Update interval
UPDATE_INTERVAL = timedelta(minutes=15)

# Sensor types
SENSOR_WEEKLY_RESET = "weekly_reset"
SENSOR_DAILY_RESET = "daily_reset"
SENSOR_SEASON_END = "season_end"
SENSOR_VAULT_COUNT = "vault_count"
SENSOR_GUARDIAN = "guardian"
SENSOR_CHARACTERS = "characters"
SENSOR_ROTATORS = "rotators"

# Bungie bucket hashes
BUCKET_POSTMASTER = 215593132

# Membership type names
MEMBERSHIP_TYPES = {
    0: "None",
    1: "Xbox",
    2: "PlayStation",
    3: "Steam",
    4: "Blizzard",
    5: "Stadia",
    6: "Epic",
    10: "Demon",
    254: "BungieNext",
}
