% Cross-check: the MATLAB/Octave tools must reproduce the numbers of the Python tools.
%   octave --eval "check_against_python('data/synthetic.bin', 'results/synthetic/summary.json')"
function check_against_python(binfile, jsonfile)
    addpath(fullfile(fileparts(mfilename('fullpath')), '..', '..', 'tools', 'matlab'));
    ref = jsondecode(fileread(jsonfile));
    r = analyze_log(binfile);

    assert(r.frames_received == ref.loss.frames_received, 'frames_received differs');
    assert(r.frames_lost == ref.loss.frames_lost, 'frames_lost differs');
    assert(r.crc_errors == ref.loss.crc_errors, 'crc_errors differs');
    assert(abs(r.jitter_rms_us - ref.timing.jitter_us.rms) < 1e-6, 'jitter rms differs');
    assert(abs(r.latency_mean_us - ref.timing.latency_us.mean) < 1e-6, 'latency differs');
    assert(max(abs(r.gyro_bias_dps - ref.imu_static.gyro_mean_dps(:).')) < 1e-4, 'gyro bias differs');
    disp('OK: MATLAB/Octave results match the Python reference');
end
