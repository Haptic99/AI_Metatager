import pytest
import subprocess
from ai_metatagger.utils.subprocess_tracker import SubprocessTracker, get_active_tracker, set_active_tracker, tracked_run

def test_tracker_singleton():
    """Test global tracker setting and getting."""
    tracker = SubprocessTracker()
    set_active_tracker(tracker)
    assert get_active_tracker() is tracker
    
    set_active_tracker(None)
    assert get_active_tracker() is None

def test_tracker_cancellation(mocker):
    """Test that cancel() kills tracked processes and prevents new ones from starting."""
    tracker = SubprocessTracker()
    
    # Mock Popen
    mock_popen = mocker.patch('ai_metatagger.utils.subprocess_tracker.subprocess.Popen')
    mock_proc = mocker.MagicMock()
    def simulate_communicate(*args, **kwargs):
        # The process is blocking here. Let's trigger a cancellation!
        tracker.cancel()
        return (b'stdout', b'stderr')
        
    mock_proc.communicate.side_effect = simulate_communicate
    mock_proc.poll.return_value = None  # Pretend it's still running
    mock_popen.return_value = mock_proc
    
    # Run a command (which will be mocked and block in communicate, triggering cancel)
    tracker.run(["fake_command"])
    
    # Verify the running process was killed
    assert mock_proc.kill.called or mock_proc.terminate.called
    assert tracker.is_cancelled is True
    
    # Verify that trying to run a new command immediately returns with an error
    mock_popen.reset_mock()
    result = tracker.run(["another_command"])
    assert result.returncode != 0
    assert not mock_popen.called  # Popen should NOT have been called again

def test_tracked_run_with_global_tracker(mocker):
    """Test the tracked_run helper function with an active global tracker."""
    tracker = SubprocessTracker()
    set_active_tracker(tracker)
    
    mock_popen = mocker.patch('ai_metatagger.utils.subprocess_tracker.subprocess.Popen')
    mock_proc = mocker.MagicMock()
    mock_proc.communicate.return_value = (b'out', b'err')
    mock_proc.returncode = 0
    mock_popen.return_value = mock_proc
    
    result = tracked_run(["echo", "hello"])
    assert result.returncode == 0
    assert mock_popen.called
    
    set_active_tracker(None)
