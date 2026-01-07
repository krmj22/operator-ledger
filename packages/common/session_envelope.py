"""
Session Envelope Contract

Defines the minimal interface between capture and ledger layers.
Ledger ingestion only depends on these fields; everything else is optional.

Critical: Ledger filters interactions where type == "user_prompt" only.
This means at least one interaction with type="user_prompt" is needed for
ledger analysis to work properly.

Contract Specification:

Required top-level fields:
    - schema_version (string): For compatibility checks
    - session_id (string): Unique identifier (SHA-256 hash)
    - start_time (string, ISO8601): Session start timestamp
    - interactions (array): List of interaction objects

Required per interaction:
    - type (string): Interaction type (ledger filters for "user_prompt")
    - timestamp (string, ISO8601): When interaction occurred
    - content (string): The actual message content
    - id (string): Unique interaction identifier

Version: 1.0.0
"""

REQUIRED_FIELDS = ['schema_version', 'session_id', 'start_time', 'interactions']
REQUIRED_INTERACTION_FIELDS = ['type', 'timestamp', 'content', 'id']
SUPPORTED_SCHEMA_VERSIONS = ['1.2.0']


def validate_session_envelope(session_json):
    """
    Validate session against minimal contract.

    This validation ensures the session JSON contains all required fields
    for ledger ingestion to work correctly. It does not validate optional
    fields or additional metadata.

    Args:
        session_json (dict): Parsed session JSON object

    Returns:
        tuple: (is_valid, warnings)
            - is_valid (bool): True if session meets minimal contract
            - warnings (list): List of warning messages (empty if no warnings)

    Examples:
        >>> valid_session = {
        ...     "schema_version": "1.2.0",
        ...     "session_id": "abc123",
        ...     "start_time": "2025-01-01T00:00:00Z",
        ...     "interactions": [
        ...         {
        ...             "id": "1",
        ...             "type": "user_prompt",
        ...             "timestamp": "2025-01-01T00:00:01Z",
        ...             "content": "test"
        ...         }
        ...     ]
        ... }
        >>> is_valid, warnings = validate_session_envelope(valid_session)
        >>> is_valid
        True
        >>> len(warnings)
        0
    """
    warnings = []

    # Check that session_json is a dict
    if not isinstance(session_json, dict):
        return False, ["Session must be a JSON object/dict"]

    # Check top-level required fields
    for field in REQUIRED_FIELDS:
        if field not in session_json:
            return False, [f"Missing required field: {field}"]

    # Check schema version
    if session_json['schema_version'] not in SUPPORTED_SCHEMA_VERSIONS:
        warnings.append(
            f"Unknown schema version: {session_json['schema_version']} "
            f"(supported: {SUPPORTED_SCHEMA_VERSIONS}). Continuing in compatibility mode."
        )

    # Check interactions array
    if not isinstance(session_json['interactions'], list):
        return False, ["'interactions' must be an array"]

    if len(session_json['interactions']) == 0:
        return False, ["'interactions' array cannot be empty"]

    # Check each interaction has required fields
    has_user_prompt = False
    for i, interaction in enumerate(session_json['interactions']):
        if not isinstance(interaction, dict):
            return False, [f"Interaction {i} must be a JSON object/dict"]

        for field in REQUIRED_INTERACTION_FIELDS:
            if field not in interaction:
                return False, [f"Interaction {i} missing required field: {field}"]

        # Track if we found at least one user_prompt
        if interaction.get('type') == 'user_prompt':
            has_user_prompt = True

    # Warn if no user_prompt type found (ledger needs at least one)
    if not has_user_prompt:
        warnings.append(
            "No user_prompt interactions found. Ledger ingestion requires "
            "at least one interaction with type='user_prompt' for analysis."
        )

    return True, warnings
