function cal = calibrate_six_position(means)
%CALIBRATE_SIX_POSITION  Accelerometer offset and sensitivity from six static positions.
%   cal = calibrate_six_position(means)
%   means is a struct with 1x3 mean readings [g] when that axis points up (+) or down (-):
%       xp xn yp yn zp zn            (e.g. means.xp = [1.07 -0.05 0.08])
%   cal.bias_g (1x3), cal.scale (1x3): a_cal = cal.scale .* (a_raw - cal.bias_g)
% Diagonal model (offset + per-axis scale); misalignment is not estimated. Same maths as
% tools/imu_daq/calibration.py.
names = {'xp','xn','yp','yn','zp','zn'};
for k = 1:6
    if ~isfield(means, names{k}), error('missing position %s', names{k}); end
end
cal.bias_g = zeros(1,3); cal.scale = zeros(1,3);
axes_ = 'xyz';
for i = 1:3
    up   = means.([axes_(i) 'p'])(i);
    down = means.([axes_(i) 'n'])(i);
    if ~(up > 0.8 && up < 1.2) || ~(down > -1.2 && down < -0.8)
        error('axis %s: readings %+.3f g and %+.3f g are not about +1 g / -1 g; check orientation and file order', ...
              axes_(i), up, down);
    end
    cal.bias_g(i) = 0.5 * (up + down);
    cal.scale(i)  = 2 / (up - down);
end
end
