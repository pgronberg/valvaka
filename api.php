<?php
// Proxies Valmyndigheten's live Riksdag results (val.se sends no CORS headers), with a short shared
// cache so every visitor doesn't hit val.se, and records a snapshot per val.se update for the
// history chart. Reached as api/results and api/history via .htaccess.
const UPSTREAM = 'https://resultat.val.se/data/resultat/val2026/RD_P.json';
const CACHE_SECONDS = 30; // the val.se CDN caches for ~60s, so fetching more often gains nothing
const USER_AGENT = 'valvaka-dashboard/1.0';
const LEFT = ['S', 'V', 'MP', 'C'];
const RIGHT = ['M', 'SD', 'KD', 'L'];
const MONTHS = ['januari', 'februari', 'mars', 'april', 'maj', 'juni', 'juli',
                'augusti', 'september', 'oktober', 'november', 'december'];

function fetch_upstream(): string|false
{
    if (function_exists('curl_init')) {
        $ch = curl_init(UPSTREAM);
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => 15,
            CURLOPT_USERAGENT => USER_AGENT,
            CURLOPT_FOLLOWLOCATION => true,
        ]);
        $body = curl_exec($ch);
        $ok = curl_getinfo($ch, CURLINFO_RESPONSE_CODE) === 200;
        curl_close($ch);
        return $ok ? $body : false;
    }
    $ctx = stream_context_create(['http' => ['timeout' => 15, 'header' => 'User-Agent: ' . USER_AGENT . "\r\n"]]);
    return @file_get_contents(UPSTREAM, false, $ctx);
}

function data_dir(): string
{
    $dir = __DIR__ . '/data';
    if (!is_dir($dir)) {
        @mkdir($dir, 0775);
    }
    return is_writable($dir) ? $dir : sys_get_temp_dir();
}

// Same shape as server.py's snapshot(): one point per val.se update
function snapshot(array $d): ?array
{
    $r = $d['rosterPaverkaMandat'] ?? null;
    $parts = explode(' ', $d['senasteUppdateringstid'] ?? '');
    if (!$r || count($parts) !== 4) {
        return null;
    }
    [$day, $month, $year, $clock] = $parts;
    $m = array_search(strtolower($month), MONTHS, true);
    if ($m === false) {
        return null;
    }
    $shares = [];
    $votes = [];
    foreach ($r['partiroster'] as $p) {
        $shares[$p['partiforkortning']] = $p['andelRoster'];
        $votes[$p['partiforkortning']] = $p['antalRoster'] ?? 0;
    }
    $total = $r['antalRoster'] ?: 0;
    $bloc = fn(array $codes) => $total ? round(array_sum(array_intersect_key($votes, array_flip($codes))) / $total * 100, 2) : 0;
    return [
        't' => sprintf('%04d-%02d-%02dT%s', $year, $m + 1, $day, $clock),
        'districts' => $d['antalValdistriktRaknade'],
        'left' => $bloc(LEFT),
        'right' => $bloc(RIGHT),
        'parties' => $shares,
    ];
}

function record_history(array $snap, string $file): void
{
    $fh = fopen($file, 'c+');
    if (!$fh) {
        return;
    }
    flock($fh, LOCK_EX);
    $history = json_decode(stream_get_contents($fh), true) ?: [];
    if (!$history || end($history)['t'] !== $snap['t']) {
        $history[] = $snap;
        ftruncate($fh, 0);
        rewind($fh);
        fwrite($fh, json_encode($history));
    }
    flock($fh, LOCK_UN);
    fclose($fh);
}

function read_history(string $file): string
{
    $fh = @fopen($file, 'r');
    if (!$fh) {
        return '[]';
    }
    flock($fh, LOCK_SH);
    $body = stream_get_contents($fh);
    flock($fh, LOCK_UN);
    fclose($fh);
    return $body ?: '[]';
}

$dir = data_dir();
$cacheFile = "$dir/valvaka_latest.json";
$historyFile = "$dir/valvaka_history.json";

foreach (['districts', 'seats'] as $generated) {
    if (!isset($_GET[$generated])) {
        continue;
    }
    // Both written every minute by cron: python3 districts.py data/districts.json
    $generatedFile = __DIR__ . "/data/$generated.json";
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    if (!is_file($generatedFile)) {
        http_response_code(503);
        echo "{\"error\":\"$generated not generated yet\"}";
        exit;
    }
    readfile($generatedFile);
    exit;
}

if (!is_file($cacheFile) || time() - filemtime($cacheFile) >= CACHE_SECONDS) {
    $body = fetch_upstream();
    $data = $body === false ? null : json_decode($body, true);
    if (is_array($data)) {
        // Write then rename so a concurrent request never reads a half-written file
        $tmp = $cacheFile . '.' . getmypid();
        file_put_contents($tmp, $body);
        rename($tmp, $cacheFile);
        if ($snap = snapshot($data)) {
            record_history($snap, $historyFile);
        }
    }
    // On failure, fall through and keep serving the last good copy
}

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

if (isset($_GET['history'])) {
    echo read_history($historyFile);
    exit;
}
if (!is_file($cacheFile)) {
    http_response_code(502);
    echo '{"error":"upstream unavailable"}';
    exit;
}
readfile($cacheFile);
