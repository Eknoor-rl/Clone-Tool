"""
Rocketlane Clone Tool - Web UI
A simple web interface to clone portals without editing property files
"""

from flask import Flask, render_template, request, jsonify, send_file
import os
import json
import tempfile
import subprocess
import threading
import time
from datetime import datetime
from typing import Dict, Any

app = Flask(__name__)
app.config['SECRET_KEY'] = 'rocketlane-migration-secret-key'

# Store the last clone result
last_clone_result = {
    "status": None,
    "output": None,
    "timestamp": None,
    "mappings": {}
}

# Store current migration state
current_migration = {
    "running": False,
    "process": None,
    "start_time": None,
    "output_file": None,
    "progress": {
        "phase": None,
        "fields_created": 0,
        "total_fields": 0
    }
}


def sanitize_portal_name(name: str) -> str:
    """
    Convert portal name to safe directory name
    Examples:
        "High Radius Prod" → "HighRadiusProd"
        "Customer-A Sandbox" → "CustomerASandbox"
    """
    return ''.join(c for c in name if c.isalnum())


def get_customer_directory(source_name: str, dest_name: str) -> str:
    """
    Generate customer directory path based on portal names
    Returns: "customers/{SourcePortal}_to_{DestPortal}/"
    """
    source_clean = sanitize_portal_name(source_name)
    dest_clean = sanitize_portal_name(dest_name)
    return f"customers/{source_clean}_to_{dest_clean}"


def migrate_legacy_files(customer_dir: str):
    """
    One-time migration: Move old mapping files to customer directory
    Only runs if old files exist in root directory
    """
    import shutil

    legacy_files = [
        'task_field_mapping.json',
        'project_field_mapping.json',
        'role_mapping.json',
        'skill_mapping.json',
        'user_mapping.json',
        'template_mapping.json',
        'migrations'
    ]

    files_to_migrate = []
    for item in legacy_files:
        if os.path.exists(item):
            files_to_migrate.append(item)

    if not files_to_migrate:
        return  # No legacy files to migrate

    # Create customer directory
    os.makedirs(customer_dir, exist_ok=True)

    # Migrate each file/directory
    print(f"\n{'='*80}")
    print("NOTICE: Legacy Data Structure Detected")
    print(f"{'='*80}")
    print(f"Migrating {len(files_to_migrate)} items to customer-based structure...")
    print(f"Destination: {customer_dir}/")

    for item in files_to_migrate:
        dest_path = os.path.join(customer_dir, item)
        print(f"  Moving: {item} → {dest_path}")
        shutil.move(item, dest_path)

    print(f"\n✅ Migration complete! All data preserved.")
    print(f"✅ Future runs will automatically use customer directories.")
    print(f"{'='*80}\n")


def create_temp_properties_file(source_config: Dict, destination_config: Dict, features: Dict = None, customer_dir: str = '') -> str:
    """Create a temporary properties file from web form data"""

    # Set default features if not provided
    if features is None:
        features = {
            'fields': True,
            'fields_task': True,
            'fields_project': True,
            'fields_user': True,
            'fields_company': True,
            'roles': True,
            'skills': True,
            'templates': True,
            'dependencies': True,
            'automations': True,
            'timesheets': True
        }

    properties_content = f"""# Temporary Properties File - Generated from Web UI
# Generated: {datetime.now().isoformat()}

# ============================================================================
# SOURCE PORTAL CONFIGURATION
# ============================================================================

# Source Portal - Basic Information
portal1.name={source_config.get('name', 'Source Portal')}
portal1.base.url={source_config['base_url']}
portal1.api.base={source_config['v1_api_base']}
portal1.v1.api.base={source_config['v1_api_base']}
portal1.api.key={source_config['api_key']}
portal1.automation.api.key={source_config.get('automation_api_key', source_config['api_key'])}

# Source Portal - API Endpoints
portal1.endpoint.fields=/api/1.0/fields
portal1.endpoint.field.detail=/api/1.0/fields/{{fieldId}}
portal1.endpoint.all.fields=/api/v1/all-fields
portal1.endpoint.field.sections=/api/v1/field-sections
portal1.endpoint.roles=/api/v1/roles
portal1.endpoint.skills=/api/v1/skill/fields
portal1.endpoint.users=/api/1.0/users
portal1.endpoint.cost.rates=/api/v1/cost-rates/users/{{userId}}
portal1.endpoint.holiday.calendar=/api/v1/holiday-calendars/{{calendarId}}
portal1.endpoint.templates=/api/v1/templates
portal1.endpoint.template.detail=/api/v1/templates/{{templateId}}
portal1.endpoint.template.dependencies=/api/v1/templates/dependency-map
portal1.endpoint.automations.global=/api/v1/automations/global
portal1.endpoint.timesheets.configuration=/api/v1/timesheets/configuration
portal1.endpoint.timesheets.categories=/api/v1/timesheets/categories
portal1.endpoint.timesheets.activity=/api/v1/timesheets/activity

# ============================================================================
# DESTINATION PORTAL CONFIGURATION
# ============================================================================

# Destination Portal - Basic Information
portal2.name={destination_config.get('name', 'Destination Portal')}
portal2.base.url={destination_config['base_url']}
portal2.api.base={destination_config['api_base']}
portal2.api.key={destination_config['api_key']}

# Destination Portal - API Endpoints
portal2.endpoint.fields=/api/1.0/fields
portal2.endpoint.field.sections=/api/v1/field-sections
portal2.endpoint.roles=/api/v1/roles
portal2.endpoint.skills=/api/v1/fields
portal2.endpoint.users=/api/v1/subscription/add-agents
portal2.endpoint.cost.rates=/api/v1/cost-rates/users/{{userId}}
portal2.endpoint.templates=/api/v1/templates
portal2.endpoint.template.detail=/api/v1/templates/{{templateId}}
portal2.endpoint.template.dependencies=/api/v1/templates/dependency-map
portal2.endpoint.automations.global=/api/v1/automations/global
portal2.endpoint.timesheets.configuration=/api/v1/timesheets/configuration
portal2.endpoint.timesheets.categories=/api/v1/timesheets/categories
portal2.endpoint.timesheets.activity=/api/v1/timesheets/activity

# ============================================================================
# MIGRATION CONFIGURATION
# ============================================================================

# Object types to migrate
migration.object.types=TASK,PROJECT,USER,COMPANY

# Choice field types
migration.choice.field.types=SINGLE_CHOICE,MULTIPLE_CHOICE

# Template migration order
migration.template.order=FORM,STATUS_UPDATE,DOCUMENT,TASK,PROJECT

# Excluded field IDs (comma-separated, leave empty to migrate all)
migration.excluded.field.ids=

# ============================================================================
# MIGRATION FEATURES (true/false)
# ============================================================================

# Enable/disable specific migration steps
migration.enable.fields={'true' if features.get('fields', True) else 'false'}
migration.enable.roles={'true' if features.get('roles', True) else 'false'}
migration.enable.skills={'true' if features.get('skills', True) else 'false'}
migration.enable.users=true
migration.enable.templates={'true' if features.get('templates', True) else 'false'}
migration.enable.dependencies={'true' if features.get('dependencies', True) else 'false'}
migration.enable.automations={'true' if features.get('automations', True) else 'false'}
migration.enable.timesheets={'true' if features.get('timesheets', True) else 'false'}

# Field object types to migrate (if fields are enabled)
migration.enable.fields.task={'true' if features.get('fields_task', True) else 'false'}
migration.enable.fields.project={'true' if features.get('fields_project', True) else 'false'}
migration.enable.fields.user={'true' if features.get('fields_user', True) else 'false'}
migration.enable.fields.company={'true' if features.get('fields_company', True) else 'false'}

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

# Customer-specific directory for mapping files
customer.directory={customer_dir}

# Log file paths (in customer directory)
logging.migration.log={customer_dir}{'/' if customer_dir else ''}migration_log.json
logging.field.mapping={customer_dir}{'/' if customer_dir else ''}field_mapping.json
logging.section.mapping={customer_dir}{'/' if customer_dir else ''}section_mapping.json
logging.role.mapping={customer_dir}{'/' if customer_dir else ''}role_mapping.json
logging.skill.mapping={customer_dir}{'/' if customer_dir else ''}skill_mapping.json
logging.user.mapping={customer_dir}{'/' if customer_dir else ''}user_mapping.json
logging.template.mapping={customer_dir}{'/' if customer_dir else ''}template_mapping.json
logging.dependency.mapping={customer_dir}{'/' if customer_dir else ''}dependency_mapping.json
logging.automation.mapping={customer_dir}{'/' if customer_dir else ''}automation_mapping.json
logging.timesheet.mapping={customer_dir}{'/' if customer_dir else ''}timesheet_mapping.json

# ============================================================================
# RATE LIMITING (seconds between API calls)
# ============================================================================

ratelimit.field.detail.fetch=0.1
ratelimit.field.creation=0.2
ratelimit.role.creation=0.2
ratelimit.skill.creation=0.2
ratelimit.user.creation=0.3
ratelimit.template.creation=0.2
ratelimit.template.detail.fetch=0.1
ratelimit.automation.creation=0.2
ratelimit.timesheet.creation=0.2
"""

    # Create temporary file
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.properties', delete=False)
    temp_file.write(properties_content)
    temp_file.close()

    return temp_file.name


@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')


def run_migration_async(temp_properties_file, dry_run, dest_api_key):
    """Run migration in background thread"""
    global current_migration, last_clone_result

    try:
        # Build command
        cmd = ['python3', 'migrate_all_with_properties.py', '--config', temp_properties_file]
        if dry_run:
            cmd.append('--dry-run')

        # Create output file for streaming
        output_file = f'migration_output_{int(time.time())}.txt'
        current_migration['output_file'] = output_file

        # Run migration process
        with open(output_file, 'w') as f:
            process = subprocess.Popen(
                cmd,
                stdout=f,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            current_migration['process'] = process

            # Wait for completion
            return_code = process.wait()

            # Migration complete
            current_migration['running'] = False

            # Read final output
            with open(output_file, 'r') as output_f:
                output = output_f.read()

            # Store result
            last_clone_result = {
                "status": "success" if return_code == 0 else "error",
                "output": output,
                "timestamp": datetime.now().isoformat(),
                "dry_run": dry_run,
                "returncode": return_code
            }

            # Read mapping files
            if return_code == 0 and not dry_run:
                mappings = {}
                mapping_files = [
                    'field_mapping.json',
                    'task_field_mapping.json',
                    'project_field_mapping.json',
                    'section_mapping.json',
                ]

                for mapping_file in mapping_files:
                    if os.path.exists(mapping_file):
                        try:
                            with open(mapping_file, 'r') as mf:
                                mappings[mapping_file] = json.load(mf)
                        except:
                            pass

                last_clone_result['mappings'] = mappings

        # Clean up temp file
        try:
            os.unlink(temp_properties_file)
        except:
            pass

    except Exception as e:
        current_migration['running'] = False
        last_clone_result = {
            "status": "error",
            "output": f"Error running migration: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }


@app.route('/run-migration', methods=['POST'])
def run_clone():
    """Start migration in background"""
    global current_migration

    try:
        # Check if migration is already running
        if current_migration['running']:
            return jsonify({
                "status": "error",
                "message": "Migration is already running"
            }), 400

        data = request.json

        # Extract configurations
        source_config = {
            'name': data['source_name'],
            'base_url': data['source_base_url'],
            'v1_api_base': data['source_v1_api_base'],
            'api_key': data['source_api_key'],
            'automation_api_key': data.get('source_automation_api_key', data['source_api_key'])
        }

        destination_config = {
            'name': data['destination_name'],
            'base_url': data['destination_base_url'],
            'api_base': data['destination_api_base'],
            'api_key': data['destination_api_key']
        }

        dry_run = data.get('dry_run', True)

        features = {
            'fields': data.get('enable_fields', True),
            'fields_task': data.get('enable_fields_task', True),
            'fields_project': data.get('enable_fields_project', True),
            'fields_user': data.get('enable_fields_user', True),
            'fields_company': data.get('enable_fields_company', True),
            'roles': data.get('enable_roles', True),
            'skills': data.get('enable_skills', True),
            'templates': data.get('enable_templates', True),
            'dependencies': data.get('enable_dependencies', True),
            'automations': data.get('enable_automations', True),
            'timesheets': data.get('enable_timesheets', True)
        }

        # NEW: Generate customer directory based on portal names
        customer_dir = get_customer_directory(source_config['name'], destination_config['name'])

        # NEW: Check for and migrate legacy files (one-time, backward compatibility)
        migrate_legacy_files(customer_dir)

        # NEW: Create customer directory if it doesn't exist
        os.makedirs(customer_dir, exist_ok=True)

        # Create temp properties file with customer directory
        temp_properties_file = create_temp_properties_file(source_config, destination_config, features, customer_dir)

        # Start migration in background
        current_migration['running'] = True
        current_migration['start_time'] = datetime.now().isoformat()
        current_migration['progress'] = {
            'phase': 'starting',
            'fields_created': 0,
            'total_fields': 0
        }

        thread = threading.Thread(
            target=run_migration_async,
            args=(temp_properties_file, dry_run, destination_config['api_key'])
        )
        thread.daemon = True
        thread.start()

        return jsonify({
            "status": "started",
            "message": "Migration started in background",
            "timestamp": current_migration['start_time']
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "output": f"Error starting migration: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }), 500


@app.route('/migration-status', methods=['GET'])
def migration_status():
    """Get current migration status"""
    global current_migration, last_clone_result

    if current_migration['running']:
        # Check field count to show progress
        try:
            import requests
            # This would need the destination API key - we'll add it to current_migration
            # For now, just return running status
            pass
        except:
            pass

        return jsonify({
            "status": "running",
            "start_time": current_migration['start_time'],
            "progress": current_migration['progress'],
            "output_file": current_migration.get('output_file')
        })
    else:
        # Migration complete or not started
        if last_clone_result.get('status'):
            return jsonify({
                "status": "complete",
                "result": last_clone_result
            })
        else:
            return jsonify({
                "status": "not_started"
            })


@app.route('/results')
def results():
    """Show clone results"""
    return render_template('results.html', result=last_clone_result)


@app.route('/download/<filename>')
def download_file(filename):
    """Download a mapping file"""
    allowed_files = [
        'migration_log.json',
        'field_mapping.json',
        'section_mapping.json',
        'role_mapping.json',
        'skill_mapping.json',
        'user_mapping.json',
        'template_mapping.json',
        'dependency_mapping.json',
        'automation_mapping.json',
        'timesheet_mapping.json'
    ]

    if filename in allowed_files and os.path.exists(filename):
        return send_file(filename, as_attachment=True)
    else:
        return "File not found", 404


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


if __name__ == '__main__':
    print("=" * 80)
    print("ROCKETLANE CLONE TOOL - WEB UI")
    print("=" * 80)
    print("\nStarting web server...")
    print("\n🌐 Open your browser and navigate to:")
    print("   http://localhost:5000")
    print("\n📝 Enter your Source and Destination portal details")
    print("   and click 'Run Clone' to start.")
    print("\n⚠️  Tip: Use 'Dry Run' first to test without making changes!")
    print("\n" + "=" * 80)

    # Disable auto-reload to prevent interrupting long-running migrations
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
