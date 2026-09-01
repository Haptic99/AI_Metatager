import pytest
from unittest.mock import mock_open
from ai_metatagger.core import logger

def test_write_review(mocker):
    # Mock datetime to always return a fixed time
    mock_now = mocker.patch('ai_metatagger.core.logger.datetime.datetime')
    mock_now.now.return_value.strftime.return_value = '2026-09-01 20:00:00'
    
    # Mock open
    m = mock_open()
    mocker.patch('builtins.open', m)
    
    # Run
    logger.write_review("Test Message")
    
    # Verify open was called correctly
    m.assert_called_once_with(logger.REVIEW_LOG, 'a', encoding='utf-8')
    m().write.assert_called_once_with("[2026-09-01 20:00:00] Test Message\n")

def test_write_log_cleanup_no_timestamp(mocker):
    m = mock_open()
    mocker.patch('builtins.open', m)
    
    logger.write_log("Direct Message", console=False, log_type='cleanup')
    
    m().write.assert_called_once_with("Direct Message\n")

def test_write_log_other_adds_timestamp(mocker):
    mock_now = mocker.patch('ai_metatagger.core.logger.datetime.datetime')
    mock_now.now.return_value.strftime.return_value = '12:00:00'
    m = mock_open()
    mocker.patch('builtins.open', m)
    
    logger.write_log("Message", console=False, log_type='other')
    
    m().write.assert_called_once_with("[12:00:00] Message\n")
