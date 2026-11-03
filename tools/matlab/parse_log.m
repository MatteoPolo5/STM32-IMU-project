function out = parse_log(filename)
%PARSE_LOG  Read a binary capture of the E3 firmware and return the valid frames.
%   out = parse_log('capture.bin')
%
%   Frames are located by the sync word A5 5A and accepted only if the CRC-16/CCITT-FALSE
%   matches, so a text banner, truncated frames and corrupted bytes are skipped.
%   Frame layout (32 bytes): see docs/protocol.md.
%
%   Returned struct fields (N = number of valid frames):
%     seq      Nx1 double   sample counter
%     t_tick   Nx1 double   DWT cycle counter at timer-interrupt entry (uint32 wraps)
%     t_done   Nx1 double   DWT cycle counter when the I2C DMA finished
%     dropped  Nx1 double   firmware's cumulative lost-sample counter
%     counts   Nx7 double   raw sensor counts: ax ay az temp gx gy gz (int16)
%     n_bad_crc             sync words whose CRC failed (corrupted frames)
%     n_garbage_bytes       bytes not belonging to any valid frame

FRAME = 32;
fid = fopen(filename, 'r');
if fid < 0, error('cannot open %s', filename); end
d = fread(fid, Inf, 'uint8=>uint8');
fclose(fid);
d = d(:);
n = numel(d);

out = struct('seq', [], 't_tick', [], 't_done', [], 'dropped', [], 'counts', zeros(0,7), ...
             'n_bad_crc', 0, 'n_garbage_bytes', n);
if n < FRAME, return; end

cand = find(d(1:end-1) == 165 & d(2:end) == 90);   % A5 5A
cand = cand(cand + FRAME - 1 <= n);
if isempty(cand), return; end

idx = double(cand) + (0:FRAME-1);                  % M x 32 indices (implicit expansion)
fr  = reshape(d(idx), size(idx));                  % M x 32 uint8
stored = double(fr(:,31)) + 256*double(fr(:,32));
ok = (crc16_rows(fr(:, 3:30)) == stored);

good = cand(ok);
% drop candidates overlapping an accepted frame (sync pattern inside a payload)
keep = false(size(good)); last_end = 0;
for k = 1:numel(good)
    if good(k) > last_end
        keep(k) = true; last_end = good(k) + FRAME - 1;
    end
end
good = good(keep);

% sync-like patterns that fail the CRC count as corrupted frames only outside accepted frames
bad = cand(~ok);
n_bad = 0;
for k = 1:numel(bad)
    inside = any(bad(k) >= good & bad(k) <= good + FRAME - 1);
    if ~inside, n_bad = n_bad + 1; end
end
if isempty(good), out.n_bad_crc = n_bad; return; end

fr = reshape(d(double(good) + (0:FRAME-1)), numel(good), FRAME);
u32 = @(c) double(fr(:,c)) + 256*double(fr(:,c+1)) + 65536*double(fr(:,c+2)) + 16777216*double(fr(:,c+3));
out.seq     = u32(3);
out.t_tick  = u32(7);
out.t_done  = u32(11);
out.dropped = double(fr(:,15)) + 256*double(fr(:,16));
raw = double(fr(:, 17:30));
v = raw(:, 1:2:end)*256 + raw(:, 2:2:end);         % big-endian 16-bit
v(v >= 32768) = v(v >= 32768) - 65536;             % two's complement
out.counts = v;
out.n_bad_crc = n_bad;
out.n_garbage_bytes = n - numel(good)*FRAME;
end

function crc = crc16_rows(rows)
% CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) of every row of a uint8 matrix.
persistent T
if isempty(T)
    T = zeros(1, 256);
    for i = 0:255
        c = i * 256;
        for b = 1:8
            if bitand(c, 32768), c = bitand(bitxor(c*2, 4129), 65535); else, c = bitand(c*2, 65535); end
        end
        T(i+1) = c;
    end
end
crc = 65535 * ones(size(rows,1), 1);
for col = 1:size(rows,2)
    idx = bitxor(floor(crc/256), double(rows(:,col)));
    crc = bitand(crc*256, 65535);
    crc = bitxor(crc, T(idx+1).');
end
end
