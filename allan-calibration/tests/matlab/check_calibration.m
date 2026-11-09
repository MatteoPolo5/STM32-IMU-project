% Octave/MATLAB check of calibrate_six_position and allan_summary on a deterministic example.
%   octave --eval "addpath('tests/matlab'); check_calibration()"
function check_calibration()
    addpath(fullfile(fileparts(mfilename('fullpath')), '..', '..', 'tools', 'matlab'));
    b = [0.07 -0.05 0.08]; k = [1.002 0.997 1.004];     % same truth as tests/python/test_calibration.py
    rd = @(u) b + u ./ k;                                % raw = bias + u / scale
    m.xp = rd([1 0 0]); m.xn = rd([-1 0 0]); m.yp = rd([0 1 0]); m.yn = rd([0 -1 0]); m.zp = rd([0 0 1]); m.zn = rd([0 0 -1]);
    cal = calibrate_six_position(m);
    assert(max(abs(cal.bias_g - b)) < 1e-12, 'bias not recovered');
    assert(max(abs(cal.scale - k)) < 1e-12, 'scale not recovered');
    u = [0.3 -0.5 sqrt(0.66)];
    a = cal.scale .* (rd(u) - cal.bias_g);
    assert(abs(norm(a) - 1) < 1e-12, 'calibrated norm is not 1');

    swapped = m; swapped.xp = m.xn; swapped.xn = m.xp;
    failed = false;
    try, calibrate_six_position(swapped); catch, failed = true; end
    assert(failed, 'swapped files must be rejected');

    % Allan: noise that follows the -1/2 slope exactly (adev = 0.003 / sqrt(tau)) -> ARW = 0.003 * 60 deg/sqrt(h), minimum not observed
    tau = logspace(-3, 2, 25)'; adev = 0.003 ./ sqrt(tau);
    s = allan_summary(tau, adev);
    assert(abs(s.arw_deg_per_sqrt_h - 0.18) < 1e-9, 'ARW wrong');
    assert(abs(s.slope_at_1s + 0.5) < 1e-9, 'slope wrong');
    assert(~s.bias_instability_observed, 'a falling curve must not report a minimum');
    adev2 = sqrt((0.003^2 ./ tau) + 1e-8 * tau);         % white noise + random walk: minimum inside the range
    s2 = allan_summary(tau, adev2);
    assert(s2.bias_instability_observed, 'a curve with a rising end must report a minimum');
    disp('OK: calibration and Allan summary behave as expected');
end
