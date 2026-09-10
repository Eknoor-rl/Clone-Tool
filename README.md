# Rocketlane Migration Tool

A Python tool to migrate all data from one Rocketlane portal to another, including fields, roles, skills, users, templates, dependencies, automations, and timesheets.

## Two Ways to Run

### Option 1: Web UI (Recommended) 🌐

**No configuration files needed!** Run the web interface and enter portal details through your browser.

```bash
# Install dependencies
pip install -r requirements.txt

# Start the web server
python3 web_ui.py
```

Then open your browser to **http://localhost:5000**

**Features:**
- ✅ Clean web interface
- ✅ No need to edit property files
- ✅ Enter Source and Destination portal details via form
- ✅ Dry run mode with checkbox
- ✅ See migration results in real-time
- ✅ Download mapping files directly

### Option 2: Command Line

Use this method if you prefer terminal or need automation.

#### 1. Update Portal Details

Edit **[portal.properties](portal.properties)**:

```properties
# Source Portal
portal1.base.url=https://YOUR-PORTAL1.rocketlane.com
portal1.v1.api.base=https://YOUR-PORTAL1.api.rocketlane.com
portal1.api.key=rl-YOUR-PORTAL1-API-KEY
portal1.automation.api.key=YOUR-AUTOMATION-KEY

# Destination Portal
portal2.base.url=https://YOUR-PORTAL2.rocketlane.com
portal2.api.base=https://YOUR-PORTAL2.api.rocketlane.com
portal2.api.key=rl-YOUR-PORTAL2-API-KEY
```

#### 2. Run Migration

```bash
# Test first (dry run)
uv run python migrate_all_with_properties.py --dry-run

# Run live migration
uv run python migrate_all_with_properties.py
```

---

## What Gets Migrated

The tool migrates **8 types** of data in order:

1. **Fields** (PROJECT, TASK, USER, COMPANY)
2. **Roles**
3. **Skills**
4. **Users** (with cost rates and holiday calendars)
5. **Templates** (with field ID remapping)
6. **Dependencies** (task/phase dependencies and dynamic conditions)
7. **Automations** (global automations)
8. **Timesheets** (configuration, categories, and activities)

## Files

### Essential Files

| File | Purpose |
|------|---------|
| **[web_ui.py](web_ui.py)** | **Web interface - run this for browser-based UI** |
| **[portal.properties](portal.properties)** | **Configuration file for command-line usage** |
| [migrate_all_with_properties.py](migrate_all_with_properties.py) | Main migration program (command-line) |
| [properties_loader.py](properties_loader.py) | Loads configuration from portal.properties |
| [analyze.py](analyze.py) | Analyzes migration logs |
| [requirements.txt](requirements.txt) | Python dependencies |

### Web UI Files

| File | Purpose |
|------|---------|
| [templates/index.html](templates/index.html) | Web interface HTML template |
| [static/style.css](static/style.css) | Web interface styles |

### Documentation

| File | Purpose |
|------|---------|
| **[QUICK_START_PROPERTIES.md](QUICK_START_PROPERTIES.md)** | **Quick start guide - start here!** |
| [PROPERTIES_MIGRATION_GUIDE.md](PROPERTIES_MIGRATION_GUIDE.md) | Detailed migration guide |
| [CONFIGURATION.md](CONFIGURATION.md) | Configuration reference |
| [README.md](README.md) | This file |

## Generated Files

After migration, these mapping files are created:

```
migration_log.json              # Complete log of all operations
field_mapping.json              # Portal 1 ↔ Portal 2 field IDs
role_mapping.json               # Portal 1 ↔ Portal 2 role IDs
skill_mapping.json              # Portal 1 ↔ Portal 2 skill IDs
user_mapping.json               # Portal 1 ↔ Portal 2 user IDs
template_mapping.json           # Portal 1 ↔ Portal 2 template IDs
dependency_mapping.json         # Portal 1 ↔ Portal 2 task/phase IDs
automation_mapping.json         # Portal 1 ↔ Portal 2 automation IDs
timesheet_mapping.json          # Timesheet configuration mappings
```

## Features

✅ **Single Configuration File** - Update portal.properties only
✅ **Complete Migration** - All 8 data types in one run
✅ **Automations Included** - Global automations migrated
✅ **Timesheets Included** - Full timesheet setup migrated
✅ **Feature Flags** - Enable/disable specific steps
✅ **ID Remapping** - All IDs automatically mapped between portals
✅ **Dry Run Mode** - Test before running live
✅ **Comprehensive Logging** - All operations tracked

## Configuration Options

### Enable/Disable Migration Steps

In [portal.properties](portal.properties):

```properties
migration.enable.fields=true
migration.enable.roles=true
migration.enable.skills=true
migration.enable.users=true
migration.enable.templates=true
migration.enable.dependencies=true
migration.enable.automations=true
migration.enable.timesheets=true
```

Set any to `false` to skip that step.

### Rate Limiting

Control delays between API calls:

```properties
ratelimit.field.creation=0.2        # 200ms between field creations
ratelimit.automation.creation=0.2   # 200ms between automations
ratelimit.timesheet.creation=0.2    # 200ms between timesheet items
```

## API Endpoints

### Portal 1 (Source) - GET Operations

```
GET  /api/1.0/fields
GET  /api/v1/roles
GET  /api/v1/skill/fields
GET  /api/1.0/users
GET  /api/v1/cost-rates/users/{userId}
GET  /api/v1/templates
GET  /api/v1/templates/{templateId}
POST /api/v1/templates/dependency-map
GET  /api/v1/automations/global
GET  /api/v1/timesheets/configuration
GET  /api/v1/timesheets/categories
GET  /api/v1/timesheets/activity
```

### Portal 2 (Destination) - POST/PUT Operations

```
POST /api/v1/fields
POST /api/v1/roles
POST /api/v1/subscription/add-agents
PUT  /api/v1/cost-rates/users/{userId}
POST /api/v1/templates
POST /api/v1/templates/dependency-map
PUT  /api/v1/templates/{templateId}
POST /api/v1/automations/global
PUT  /api/v1/timesheets/configuration
POST /api/v1/timesheets/categories
POST /api/v1/timesheets/activity
```

## Examples

### Basic Migration

```bash
# Update portal.properties with your portal details

# Test with dry run
uv run python migrate_all_with_properties.py --dry-run

# Run live migration
uv run python migrate_all_with_properties.py
```

### Using Custom Properties File

```bash
# Use a different properties file
uv run python migrate_all_with_properties.py --config my-portal.properties --dry-run
```

### Analyze Results

```bash
# Analyze migration logs
uv run python analyze.py

# Check specific mappings
cat automation_mapping.json | jq '.total_mappings'
cat timesheet_mapping.json | jq '.mappings'
```

## Troubleshooting

### Issue: Properties file not found

```bash
# Check you're in the right directory
cd rocketlane-migrator
ls portal.properties
```

### Issue: Authentication error

Check API keys in portal.properties are correct:
- `portal1.api.key`
- `portal1.automation.api.key`
- `portal2.api.key`

### Issue: Some items not migrating

1. Check feature flags in portal.properties
2. Review migration_log.json for errors
3. Verify permissions in Portal 2

## Requirements

- Python 3.9+
- uv package manager
- Rocketlane API access for both portals

## Installation

```bash
# Clone or navigate to the directory
cd rocketlane-migrator

# Dependencies are managed by uv
# They will be installed automatically when you run the script
```

## Support

For detailed information, see:
- **[QUICK_START_PROPERTIES.md](QUICK_START_PROPERTIES.md)** - Quick start guide
- **[PROPERTIES_MIGRATION_GUIDE.md](PROPERTIES_MIGRATION_GUIDE.md)** - Detailed guide
- **[CONFIGURATION.md](CONFIGURATION.md)** - Configuration reference

## Summary

1. **Update** [portal.properties](portal.properties) with your portal URLs and API keys
2. **Run** `uv run python migrate_all_with_properties.py --dry-run` to test
3. **Run** `uv run python migrate_all_with_properties.py` for live migration
4. **Check** mapping files for ID mappings and migration_log.json for any errors

All 8 data types (fields, roles, skills, users, templates, dependencies, automations, timesheets) are migrated automatically!
