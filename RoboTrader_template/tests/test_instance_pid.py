from main import pid_file_name

def test_default_pid_backward_compat():
    assert pid_file_name("default") == "robotrader.pid"

def test_instance_pid():
    assert pid_file_name("rs_leader") == "robotrader_rs_leader.pid"
