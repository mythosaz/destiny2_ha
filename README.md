# Destiny 2 Home Assistant Integration

A custom Home Assistant integration that connects to the Bungie API using OAuth2 to provide Destiny 2 game data as sensors.

## Features

- **Weekly Reset Timer**: Tracks the next weekly reset (Tuesday 17:00 UTC)
- **Daily Reset Timer**: Tracks the next daily reset (17:00 UTC)
- **Season End Date**: Displays when the current season ends
- **Vault Item Count**: Shows how many items are in your vault with capacity tracking

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL and select "Integration" as the category
6. Click "Install"
7. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/destiny2` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Configuration

### Prerequisites

Before setting up this integration, you need to create a Bungie API application:

1. Go to [Bungie Application Portal](https://www.bungie.net/en/Application)
2. Create a new application
3. Set the OAuth Client Type to "Confidential"
4. Set the Redirect URL to: `https://YOUR_HOME_ASSISTANT_URL/auth/external/callback`
5. Note down your **API Key**, **OAuth Client ID**, and **OAuth Client Secret**

### Setup

1. In Home Assistant, go to **Configuration** → **Integrations**
2. Click the **+ Add Integration** button
3. Search for "Destiny 2"
4. Enter your Bungie API credentials:
   - API Key
   - OAuth Client ID
   - OAuth Client Secret
5. You'll be redirected to Bungie to authorize the application
6. After authorization, the integration will be set up and sensors will appear

## Sensors

### Weekly Reset
- **Entity ID**: `sensor.destiny2_weekly_reset`
- **Type**: Timestamp
- **Description**: Next Tuesday 17:00 UTC
- **Attributes**:
  - `days_until`: Days until reset
  - `hours_until`: Hours until reset
  - `reset_day`: "Tuesday"
  - `reset_time_utc`: "17:00"

### Daily Reset
- **Entity ID**: `sensor.destiny2_daily_reset`
- **Type**: Timestamp
- **Description**: Next 17:00 UTC
- **Attributes**:
  - `hours_until`: Hours until reset
  - `minutes_until`: Minutes until reset
  - `reset_time_utc`: "17:00"

### Season End
- **Entity ID**: `sensor.destiny2_season_end`
- **Type**: Timestamp
- **Description**: When the current season ends
- **Attributes**:
  - `days_until`: Days until season ends

### Vault Count
- **Entity ID**: `sensor.destiny2_vault_count`
- **Type**: Measurement
- **Unit**: items
- **Description**: Number of items in your vault
- **Attributes**:
  - `max_capacity`: 600
  - `remaining_space`: Items remaining before vault is full
  - `percent_full`: Percentage of vault capacity used

## Authentication

This integration uses OAuth2 with the Bungie API. Your access token is automatically refreshed when needed. Both the API Key (in `X-API-Key` header) and OAuth Bearer token are required for authenticated Bungie API endpoints.

## Data Updates

The integration polls the Bungie API every 15 minutes to update sensor data. Reset times are calculated locally and don't require API calls.

## Troubleshooting

### Integration fails to authenticate
- Verify your API credentials are correct
- Ensure your Redirect URL in the Bungie application matches your Home Assistant URL
- Check that your Home Assistant instance is accessible at the configured URL

### Sensors show "Unavailable"
- Check the Home Assistant logs for errors
- Verify your Bungie account has Destiny 2 characters
- Ensure the integration has valid OAuth tokens

### Token refresh errors
- The integration will attempt to refresh tokens automatically
- If refresh fails, you may need to remove and re-add the integration

## License

MIT License - See [LICENSE](LICENSE) file for details

## Credits

- Built for Home Assistant
- Uses the [Bungie API](https://bungie-net.github.io/multi/index.html)

## Contributing

Issues and pull requests are welcome!
