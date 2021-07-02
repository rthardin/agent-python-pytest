"""This modules includes unit tests for the plugin."""

from _pytest.config.argparsing import Parser
import pytest
from delayed_assert import expect, assert_expectations
from requests.exceptions import RequestException
from six.moves import mock

from reportportal_client.errors import ResponseError
from pytest_reportportal.config import AgentConfig
from pytest_reportportal.listener import RPReportListener
from pytest_reportportal.plugin import (
    is_master,
    pytest_addoption,
    pytest_configure,
    pytest_collection_finish,
    pytest_sessionstart,
    pytest_sessionfinish,
    pytest_unconfigure,
    wait_launch
)
from pytest_reportportal.service import PyTestServiceClass


def test_is_master(mocked_config):
    """Test is_master() function for the correct responses."""
    mocked_config.workerinput = None
    expect(is_master(mocked_config) is False)
    delattr(mocked_config, 'workerinput')
    expect(is_master(mocked_config) is True)
    assert_expectations()


@mock.patch('pytest_reportportal.RPLogger.handle')
@pytest.mark.parametrize('log_level', ('info', 'debug', 'warning', 'error'))
def test_logger_handle_attachment(mock_handler, logger, log_level):
    """Test logger call for different log levels with some text attachment."""
    log_call = getattr(logger, log_level)
    attachment = 'Some {} attachment'.format(log_level)
    log_call("Some {} message".format(log_level), attachment=attachment)
    expect(mock_handler.call_count == 1,
           'logger.handle called more than 1 time')
    expect(getattr(mock_handler.call_args[0][0], "attachment") == attachment,
           'record.attachment in args doesn\'t match real value')
    assert_expectations()


@mock.patch('pytest_reportportal.RPLogger.handle')
@pytest.mark.parametrize('log_level', ('info', 'debug', 'warning', 'error'))
def test_logger_handle_no_attachment(mock_handler, logger, log_level):
    """Test logger call for different log levels without any attachment."""
    log_call = getattr(logger, log_level)
    log_call('Some {} message'.format(log_level))
    expect(mock_handler.call_count == 1,
           'logger.handle called more than 1 time')
    expect(getattr(mock_handler.call_args[0][0], 'attachment') is None,
           'record.attachment in args is not None')
    assert_expectations()


def test_portal_on_maintenance(mocked_session):
    """Test session configuration if RP is in maintenance mode.

    :param mocked_session: pytest fixture
    """
    mocked_session.config.option = mock.Mock()
    mocked_session.config._reporter_config = mock.Mock()
    mocked_session.config.py_test_service = mock.Mock()
    mocked_session.config.py_test_service.init_service.side_effect = \
        ResponseError("<title>Report Portal - Maintenance</title>")
    pytest_sessionstart(mocked_session)
    assert mocked_session.config.py_test_service.rp is None


@mock.patch('pytest_reportportal.config.get_actual_log_level',
            mock.Mock(return_value=0))
@mock.patch('pytest_reportportal.plugin.requests.get', mock.Mock())
def test_pytest_configure(mocked_config):
    """Test plugin successful configuration.

    :param mocked_get:    Instance of the MagicMock
    :param mocked_config: Pytest fixture
    """
    mocked_config.getoption.side_effect = (False, False)
    mocked_config.option = mock.Mock()
    mocked_config.option.rp_enabled = True
    mocked_config.option.rp_project = None
    pytest_configure(mocked_config)
    expect(mocked_config._reportportal_configured is True)
    expect(
        lambda: isinstance(mocked_config.py_test_service, PyTestServiceClass))
    expect(
        lambda: isinstance(mocked_config._reporter, RPReportListener))
    assert_expectations()


@mock.patch('pytest_reportportal.plugin.requests.get')
def test_pytest_configure_dry_run(mocked_config):
    """Test plugin configuration in case of dry-run execution."""
    mocked_config.getoption.return_value = True
    pytest_configure(mocked_config)
    assert mocked_config._reportportal_configured is False


@mock.patch('pytest_reportportal.plugin.requests.get', mock.Mock())
@mock.patch('pytest_reportportal.config.get_actual_log_level', mock.Mock())
def test_pytest_configure_misssing_major_rp_options(mocked_config):
    """Test plugin configuration in case of missing required input options.

    The value of the _reportportal_configured attribute of the pytest Config
    object should be changed to False, stopping plugin configuration, if any of
    the following options were not set: rp_endpoint, rp_project, rp_uuid.
    :param mocked_config: Pytest fixture
    """
    mocked_config.getoption.side_effect = (False, False)
    mocked_config.option = mock.Mock()
    mocked_config.option.rp_enabled = True
    mocked_config.getini.return_value = 0
    pytest_configure(mocked_config)
    assert mocked_config._reportportal_configured is False


@mock.patch('pytest_reportportal.config.get_actual_log_level', mock.Mock())
@mock.patch('pytest_reportportal.plugin.requests.get')
def test_pytest_configure_on_conn_error(mocked_get, mocked_config):
    """Test plugin configuration in case of HTTP error.

    The value of the _reportportal_configured attribute of the pytest Config
    object should be changed to False, stopping plugin configuration, if HTTP
    error occurs getting HTTP response from the ReportPortal.
    :param mocked_get:    Instance of the MagicMock
    :param mocked_config: Pytest fixture
    """
    mock_response = mock.Mock()
    mock_response.raise_for_status.side_effect = RequestException()
    mocked_get.return_value = mock_response
    mocked_config.getoption.side_effect = (False, False)
    mocked_config.option = mock.Mock()
    mocked_config.option.rp_enabled = True
    pytest_configure(mocked_config)
    assert mocked_config._reportportal_configured is False


@mock.patch('pytest_reportportal.plugin.LAUNCH_WAIT_TIMEOUT', 1)
@mock.patch('pytest_reportportal.plugin.time')
def test_wait_launch(time_mock):
    """Test wait_launch() function for the correct behavior."""
    time_mock.time.side_effect = [0, 1, 2]
    rp_client = mock.Mock()
    rp_client.launch_id = None
    with pytest.raises(Exception) as err:
        wait_launch(rp_client)
    assert str(err.value) == 'Launch has not started.'


def test_pytest_collection_finish(mocked_session):
    """Test collection_finish with the configured RP plugin.

    :param mocked_session: pytest fixture
    """
    mocked_session.config.py_test_service = mock.Mock()
    pytest_collection_finish(mocked_session)
    mocked_session.config.py_test_service.collect_tests. \
        assert_called_with(mocked_session)


@mock.patch('pytest_reportportal.config.get_actual_log_level', mock.Mock())
@mock.patch('pytest_reportportal.plugin.is_master', mock.Mock())
@mock.patch('pytest_reportportal.plugin.wait_launch')
def test_pytest_sessionstart(mocked_wait, mocked_session):
    """Test session configuration if RP plugin is correctly configured.

    :param mocked_wait:    Mocked wait_launch function
    :param mocked_session: pytest fixture
    """
    mocked_session.config.pluginmanager.hasplugin.return_value = True
    mocked_session.config.option = mock.Mock()
    mocked_session.config._reporter_config = mock.Mock(
        spec=AgentConfig(mocked_session.config))
    mocked_session.config._reporter_config.rp_launch_attributes = []
    mocked_session.config._reporter_config.rp_launch_id = None
    mocked_session.config.py_test_service = mock.Mock()
    pytest_sessionstart(mocked_session)
    expect(lambda: mocked_session.config.py_test_service.init_service.called)
    expect(lambda: mocked_session.config.py_test_service.rp is not None)
    expect(lambda: mocked_session.config.py_test_service.start_launch.called)
    expect(lambda: mocked_wait.called)
    assert_expectations()


@mock.patch('pytest_reportportal.config.get_actual_log_level', mock.Mock())
@mock.patch('pytest_reportportal.plugin.is_master', mock.Mock())
@mock.patch('pytest_reportportal.plugin.wait_launch')
def test_pytest_sessionstart_with_launch_id(mocked_session):
    """Test session configuration if RP launch ID is set via command-line.

    :param mocked_session: pytest fixture
    """
    mocked_session.config.pluginmanager.hasplugin.return_value = True
    mocked_session.config.option = mock.Mock()
    mocked_session.config._reporter_config = mock.Mock(
        spec=AgentConfig(mocked_session.config))
    mocked_session.config._reporter_config.rp_launch_attributes = []
    mocked_session.config._reporter_config.rp_launch_id = 1
    mocked_session.config.py_test_service = mock.Mock()
    pytest_sessionstart(mocked_session)
    expect(lambda: mocked_session.config.py_test_service.start_launch.
           assert_not_called())
    assert_expectations()


@mock.patch('pytest_reportportal.plugin.is_master', mock.Mock())
def test_pytest_sessionfinish(mocked_session):
    """Test sessionfinish with the configured RP plugin.

    :param mocked_session: pytest fixture
    """
    mocked_session.config.option = mock.Mock()
    mocked_session.config.py_test_service = mock.Mock()
    mocked_session.config.option.rp_launch_id = None
    pytest_sessionfinish(mocked_session)
    assert mocked_session.config.py_test_service.finish_launch.called


def test_pytest_unconfigure(mocked_config):
    """Test unconfigure with the configured RP plugin.

    :param mocked_config: pytest fixture
    """
    mocked_config._reporter = mock.Mock()
    mocked_config.pluginmanager.unregister = mock.Mock()
    pytest_unconfigure(mocked_config)
    assert not hasattr(mocked_config, '_reporter')


def test_pytest_addoption_adds_correct_ini_file_arguments():
    """Test the correct list of options are available in the .ini file."""
    expected_argument_names = (
        'rp_log_level',
        'rp_uuid',
        'rp_endpoint',
        'rp_project',
        'rp_launch',
        'rp_launch_id',
        'rp_launch_attributes',
        'rp_tests_attributes',
        'rp_launch_description',
        'rp_log_batch_size',
        'rp_ignore_errors',
        'rp_ignore_attributes',
        'rp_is_skipped_an_issue',
        'rp_hierarchy_dirs_level',
        'rp_hierarchy_dirs',
        'rp_hierarchy_module',
        'rp_hierarchy_class',
        'rp_hierarchy_parametrize',
        'rp_issue_marks',
        'rp_issue_system_url',
        'rp_verify_ssl',
        'rp_display_suite_test_file',
        'rp_issue_id_marks',
        'rp_parent_item_id',
        'retries',
        'rp_rerun',
        'rp_rerun_of'
    )
    mock_parser = mock.MagicMock(spec=Parser)

    pytest_addoption(mock_parser)

    added_argument_names = []
    for args, kwargs in mock_parser.addini.call_args_list:
        added_argument_names.append(args[0] if args else kwargs.get("name"))
    assert tuple(added_argument_names) == expected_argument_names


def test_pytest_addoption_adds_correct_command_line_arguments():
    """Test the correct list of options are available in the command line."""
    expected_argument_names = (
        '--rp-launch',
        '--rp-launch-id',
        '--rp-launch-description',
        '--rp-rerun',
        '--rp-rerun-of',
        '--rp-parent-item-id',
        '--rp-project',
        '--reportportal',
        '--rp-log-level'
    )
    mock_parser = mock.MagicMock(spec=Parser)
    mock_reporting_group = mock_parser.getgroup.return_value

    pytest_addoption(mock_parser)

    mock_parser.getgroup.assert_called_once_with("reporting")
    added_argument_names = []
    for args, kwargs in mock_reporting_group.addoption.call_args_list:
        added_argument_names.append(args[0] if args else kwargs.get("name"))
    assert tuple(added_argument_names) == expected_argument_names
