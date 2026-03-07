from discord_codex_bridge.shortcuts import ShortcutCommand, build_running_shortcut_help, parse_shortcut_command


def test_parse_esc_command():
    assert parse_shortcut_command('$esc') == ShortcutCommand(name='esc', argument='')


def test_parse_queue_command_with_payload():
    assert parse_shortcut_command('$q  ship it  ') == ShortcutCommand(name='queue', argument='ship it')


def test_parse_queue_clear_command():
    assert parse_shortcut_command('$qx') == ShortcutCommand(name='queue_clear', argument='')


def test_parse_insert_command_with_payload():
    assert parse_shortcut_command('$insert refine the last section') == ShortcutCommand(
        name='insert',
        argument='refine the last section',
    )


def test_parse_returns_none_for_normal_message():
    assert parse_shortcut_command('hello codex') is None


def test_running_help_includes_latest_output():
    text = build_running_shortcut_help('line1\nline2')

    assert '$esc' in text
    assert '$q <text>' in text
    assert '$qx' in text
    assert '$insert <text>' in text
    assert 'line1' in text
    assert 'line2' in text
