package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/shirou/gopsutil/v4/cpu"
	"github.com/shirou/gopsutil/v4/disk"
	"github.com/shirou/gopsutil/v4/host"
	"github.com/shirou/gopsutil/v4/mem"
	gnet "github.com/shirou/gopsutil/v4/net"
	"github.com/shirou/gopsutil/v4/process"
)

const version = "0.4.0"
const serviceName = "SentinelViewAgent"

type config struct {
	ServerURL     string         `json:"server_url"`
	AgentID       string         `json:"agent_id,omitempty"`
	AgentToken    string         `json:"agent_token,omitempty"`
	DeviceID      string         `json:"device_id,omitempty"`
	Site          string         `json:"site,omitempty"`
	Tags          []string       `json:"tags,omitempty"`
	PolicyID      string         `json:"policy_id,omitempty"`
	PolicyVersion int            `json:"policy_version,omitempty"`
	Policy        map[string]any `json:"policy,omitempty"`
}

type enrollRequest struct {
	EnrollmentToken string   `json:"enrollment_token"`
	Hostname        string   `json:"hostname"`
	OSName          string   `json:"os_name"`
	Arch            string   `json:"arch"`
	Version         string   `json:"version"`
	IPAddress       string   `json:"ip_address,omitempty"`
	Site            string   `json:"site,omitempty"`
	Tags            []string `json:"tags"`
}

type enrollResponse struct {
	AgentID       string         `json:"agent_id"`
	DeviceID      string         `json:"device_id"`
	AgentToken    string         `json:"agent_token"`
	PolicyID      string         `json:"policy_id"`
	PolicyVersion int            `json:"policy_version"`
	Policy        map[string]any `json:"policy"`
}

type checkinResponse struct {
	Status        string         `json:"status"`
	PolicyID      string         `json:"policy_id"`
	PolicyVersion int            `json:"policy_version"`
	Policy        map[string]any `json:"policy"`
}

type diskMetric struct {
	Mountpoint   string  `json:"mountpoint"`
	Fstype       string  `json:"fstype"`
	TotalBytes   uint64  `json:"total_bytes"`
	UsedBytes    uint64  `json:"used_bytes"`
	UsagePercent float64 `json:"usage_percent"`
}

type interfaceMetric struct {
	Name               string `json:"name"`
	ReceiveBytesTotal  uint64 `json:"receive_bytes_total"`
	TransmitBytesTotal uint64 `json:"transmit_bytes_total"`
}

type telemetry struct {
	CollectedAt        time.Time         `json:"collected_at"`
	CPUUsagePercent    *float64          `json:"cpu_usage_percent,omitempty"`
	MemoryTotalBytes   *uint64           `json:"memory_total_bytes,omitempty"`
	MemoryUsedBytes    *uint64           `json:"memory_used_bytes,omitempty"`
	MemoryUsagePercent *float64          `json:"memory_usage_percent,omitempty"`
	UptimeSeconds      *uint64           `json:"uptime_seconds,omitempty"`
	ProcessCount       *int              `json:"process_count,omitempty"`
	Disks              []diskMetric      `json:"disks"`
	Interfaces         []interfaceMetric `json:"interfaces"`
}

var httpClient = &http.Client{Timeout: 15 * time.Second}
var logOnce sync.Once

func defaultConfigPath() string {
	if v := os.Getenv("SENTINEL_CONFIG"); v != "" {
		return v
	}
	if runtime.GOOS == "windows" {
		base := os.Getenv("ProgramData")
		if base == "" {
			base = `C:\ProgramData`
		}
		return filepath.Join(base, "SentinelView", "agent.json")
	}
	return "/etc/sentinelview/agent.json"
}

func installedBinaryPath() string {
	if runtime.GOOS == "windows" {
		base := os.Getenv("ProgramFiles")
		if base == "" {
			base = `C:\Program Files`
		}
		return filepath.Join(base, "SentinelView", "sentinel-agent.exe")
	}
	return "/usr/local/bin/sentinel-agent"
}

func logPath() string {
	if runtime.GOOS == "windows" {
		base := os.Getenv("ProgramData")
		if base == "" {
			base = `C:\ProgramData`
		}
		return filepath.Join(base, "SentinelView", "logs", "agent.log")
	}
	return "/var/log/sentinelview/agent.log"
}

func configureLogging() {
	logOnce.Do(func() {
		path := logPath()
		if err := os.MkdirAll(filepath.Dir(path), 0755); err == nil {
			if f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644); err == nil {
				log.SetOutput(io.MultiWriter(os.Stderr, f))
			}
		}
		log.SetFlags(log.LstdFlags | log.LUTC)
	})
}

func loadConfig() (config, error) {
	var cfg config
	b, err := os.ReadFile(defaultConfigPath())
	if err != nil {
		return cfg, err
	}
	if err := json.Unmarshal(b, &cfg); err != nil {
		return cfg, err
	}
	return cfg, nil
}

func saveConfig(cfg config) error {
	path := defaultConfigPath()
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}
	b, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, b, 0600)
}

func copySelf(dst string) error {
	src, err := os.Executable()
	if err != nil {
		return err
	}
	src, _ = filepath.EvalSymlinks(src)
	if filepath.Clean(src) == filepath.Clean(dst) {
		return nil
	}
	if err := os.MkdirAll(filepath.Dir(dst), 0755); err != nil {
		return err
	}
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.OpenFile(dst, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0755)
	if err != nil {
		return err
	}
	if _, err = io.Copy(out, in); err != nil {
		out.Close()
		return err
	}
	return out.Close()
}

func privateIP() string {
	ifaces, err := net.Interfaces()
	if err != nil {
		return ""
	}
	for _, iface := range ifaces {
		if iface.Flags&net.FlagUp == 0 || iface.Flags&net.FlagLoopback != 0 {
			continue
		}
		addrs, _ := iface.Addrs()
		for _, addr := range addrs {
			var ip net.IP
			switch v := addr.(type) {
			case *net.IPNet:
				ip = v.IP
			case *net.IPAddr:
				ip = v.IP
			}
			if ip == nil || ip.To4() == nil || ip.IsLoopback() {
				continue
			}
			if ip.IsPrivate() {
				return ip.String()
			}
		}
	}
	return ""
}

func apiJSON(ctx context.Context, method, url, bearer string, payload any, result any) error {
	var body io.Reader
	if payload != nil {
		b, err := json.Marshal(payload)
		if err != nil {
			return err
		}
		body = bytes.NewReader(b)
	}
	req, err := http.NewRequestWithContext(ctx, method, url, body)
	if err != nil {
		return err
	}
	if payload != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if bearer != "" {
		req.Header.Set("Authorization", "Bearer "+bearer)
	}
	resp, err := httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		msg, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return fmt.Errorf("server returned %s: %s", resp.Status, strings.TrimSpace(string(msg)))
	}
	if result != nil {
		return json.NewDecoder(resp.Body).Decode(result)
	}
	return nil
}

func enroll(cfg *config, token string) error {
	if strings.TrimSpace(cfg.ServerURL) == "" {
		return errors.New("server URL is required")
	}
	if strings.TrimSpace(token) == "" {
		return errors.New("enrollment token is required")
	}
	hostname, _ := os.Hostname()
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	var out enrollResponse
	err := apiJSON(ctx, http.MethodPost, strings.TrimRight(cfg.ServerURL, "/")+"/api/v1/agents/enroll", "", enrollRequest{
		EnrollmentToken: token, Hostname: hostname, OSName: runtime.GOOS, Arch: runtime.GOARCH,
		Version: version, IPAddress: privateIP(), Site: cfg.Site, Tags: cfg.Tags,
	}, &out)
	if err != nil {
		return err
	}
	cfg.AgentID = out.AgentID
	cfg.DeviceID = out.DeviceID
	cfg.AgentToken = out.AgentToken
	cfg.PolicyID = out.PolicyID
	cfg.PolicyVersion = out.PolicyVersion
	cfg.Policy = out.Policy
	return saveConfig(*cfg)
}

func boolPolicy(cfg config, key string, def bool) bool {
	if cfg.Policy == nil {
		return def
	}
	v, ok := cfg.Policy[key]
	if !ok {
		return def
	}
	b, ok := v.(bool)
	if !ok {
		return def
	}
	return b
}

func intPolicy(cfg config, key string, def int) int {
	if cfg.Policy == nil {
		return def
	}
	v, ok := cfg.Policy[key]
	if !ok {
		return def
	}
	switch n := v.(type) {
	case float64:
		return int(n)
	case int:
		return n
	case json.Number:
		i, _ := strconv.Atoi(n.String())
		return i
	}
	return def
}

func collectTelemetry(cfg config) telemetry {
	t := telemetry{CollectedAt: time.Now().UTC(), Disks: []diskMetric{}, Interfaces: []interfaceMetric{}}
	if boolPolicy(cfg, "collect_cpu", true) {
		if vals, err := cpu.Percent(500*time.Millisecond, false); err == nil && len(vals) > 0 {
			v := vals[0]
			t.CPUUsagePercent = &v
		}
	}
	if boolPolicy(cfg, "collect_memory", true) {
		if v, err := mem.VirtualMemory(); err == nil {
			total := v.Total
			used := v.Used
			pct := v.UsedPercent
			t.MemoryTotalBytes = &total
			t.MemoryUsedBytes = &used
			t.MemoryUsagePercent = &pct
		}
	}
	if boolPolicy(cfg, "collect_disk", true) {
		if parts, err := disk.Partitions(false); err == nil {
			seen := map[string]bool{}
			for _, p := range parts {
				if seen[p.Mountpoint] {
					continue
				}
				seen[p.Mountpoint] = true
				if u, err := disk.Usage(p.Mountpoint); err == nil {
					t.Disks = append(t.Disks, diskMetric{p.Mountpoint, p.Fstype, u.Total, u.Used, u.UsedPercent})
				}
			}
		}
	}
	if boolPolicy(cfg, "collect_network", true) {
		if nics, err := gnet.IOCounters(true); err == nil {
			for _, n := range nics {
				t.Interfaces = append(t.Interfaces, interfaceMetric{n.Name, n.BytesRecv, n.BytesSent})
			}
		}
	}
	if up, err := host.Uptime(); err == nil {
		t.UptimeSeconds = &up
	}
	if boolPolicy(cfg, "collect_process_count", true) {
		if ps, err := process.Pids(); err == nil {
			n := len(ps)
			t.ProcessCount = &n
		}
	}
	return t
}

func sendTelemetry(ctx context.Context, cfg config) error {
	t := collectTelemetry(cfg)
	return apiJSON(ctx, http.MethodPost, strings.TrimRight(cfg.ServerURL, "/")+"/api/v1/agents/telemetry", cfg.AgentToken, t, nil)
}

func checkin(ctx context.Context, cfg *config) error {
	hostname, _ := os.Hostname()
	var out checkinResponse
	err := apiJSON(ctx, http.MethodPost, strings.TrimRight(cfg.ServerURL, "/")+"/api/v1/agents/checkin", cfg.AgentToken,
		map[string]any{"hostname": hostname, "version": version, "ip_address": privateIP()}, &out)
	if err != nil {
		return err
	}
	if out.PolicyVersion != cfg.PolicyVersion || out.PolicyID != cfg.PolicyID {
		cfg.PolicyID = out.PolicyID
		cfg.PolicyVersion = out.PolicyVersion
		cfg.Policy = out.Policy
		if err := saveConfig(*cfg); err != nil {
			log.Printf("save policy: %v", err)
		}
		log.Printf("applied policy %s version %d", cfg.PolicyID, cfg.PolicyVersion)
	}
	return nil
}

func localDebugServer(ctx context.Context, cfg config) {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprint(w, `{"status":"ok","version":"`+version+`"}`)
	})
	mux.HandleFunc("/metrics", func(w http.ResponseWriter, _ *http.Request) {
		t := collectTelemetry(cfg)
		w.Header().Set("Content-Type", "text/plain; version=0.0.4")
		if t.CPUUsagePercent != nil {
			fmt.Fprintf(w, "sentinel_cpu_usage_percent %f\n", *t.CPUUsagePercent)
		}
		if t.MemoryUsagePercent != nil {
			fmt.Fprintf(w, "sentinel_memory_usage_percent %f\n", *t.MemoryUsagePercent)
		}
		if t.UptimeSeconds != nil {
			fmt.Fprintf(w, "sentinel_uptime_seconds %d\n", *t.UptimeSeconds)
		}
		if t.ProcessCount != nil {
			fmt.Fprintf(w, "sentinel_process_count %d\n", *t.ProcessCount)
		}
	})
	srv := &http.Server{Addr: "127.0.0.1:9123", Handler: mux}
	go func() {
		<-ctx.Done()
		c, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		_ = srv.Shutdown(c)
	}()
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Printf("debug endpoint: %v", err)
	}
}

func runAgent(ctx context.Context, cfg config) error {
	if cfg.AgentID == "" || cfg.AgentToken == "" {
		return errors.New("agent is not enrolled; run 'sentinel-agent enroll' or install with a token")
	}
	configureLogging()
	log.Printf("SentinelView Agent %s starting; agent_id=%s server=%s", version, cfg.AgentID, cfg.ServerURL)
	go localDebugServer(ctx, cfg)
	if c, cancel := context.WithTimeout(ctx, 10*time.Second); c.Err() == nil {
		if err := checkin(c, &cfg); err != nil {
			log.Printf("initial check-in failed: %v", err)
		}
		cancel()
	}
	telemetryEvery := time.Duration(intPolicy(cfg, "telemetry_interval_seconds", 15)) * time.Second
	checkinEvery := time.Duration(intPolicy(cfg, "checkin_interval_seconds", 30)) * time.Second
	telTimer := time.NewTimer(1 * time.Second)
	chkTimer := time.NewTimer(checkinEvery)
	defer telTimer.Stop()
	defer chkTimer.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-telTimer.C:
			c, cancel := context.WithTimeout(ctx, 20*time.Second)
			err := sendTelemetry(c, cfg)
			cancel()
			if err != nil {
				log.Printf("telemetry failed: %v", err)
			}
			telemetryEvery = time.Duration(intPolicy(cfg, "telemetry_interval_seconds", 15)) * time.Second
			telTimer.Reset(telemetryEvery)
		case <-chkTimer.C:
			c, cancel := context.WithTimeout(ctx, 15*time.Second)
			err := checkin(c, &cfg)
			cancel()
			if err != nil {
				log.Printf("check-in failed: %v", err)
			}
			checkinEvery = time.Duration(intPolicy(cfg, "checkin_interval_seconds", 30)) * time.Second
			chkTimer.Reset(checkinEvery)
		}
	}
}

func parseCommon(fs *flag.FlagSet, cfg *config) (*string, *string, *string, *string) {
	server := fs.String("server", cfg.ServerURL, "SentinelView control URL")
	token := fs.String("token", "", "one-time enrollment token")
	site := fs.String("site", cfg.Site, "site name")
	tags := fs.String("tags", strings.Join(cfg.Tags, ","), "comma separated tags")
	return server, token, site, tags
}

func tagsFrom(raw string) []string {
	var out []string
	for _, t := range strings.Split(raw, ",") {
		t = strings.TrimSpace(t)
		if t != "" {
			out = append(out, t)
		}
	}
	return out
}

func installCommand(args []string) error {
	var cfg config
	if existing, err := loadConfig(); err == nil {
		cfg = existing
	}
	fs := flag.NewFlagSet("install", flag.ContinueOnError)
	server, token, site, tags := parseCommon(fs, &cfg)
	if err := fs.Parse(args); err != nil {
		return err
	}
	cfg.ServerURL = strings.TrimRight(*server, "/")
	cfg.Site = *site
	cfg.Tags = tagsFrom(*tags)
	if err := enroll(&cfg, *token); err != nil {
		return fmt.Errorf("enrollment failed; installation rolled back: %w", err)
	}
	dst := installedBinaryPath()
	serviceExists := false
	if _, statusErr := serviceStatus(); statusErr == nil {
		serviceExists = true
		_ = stopService()
	}
	if err := copySelf(dst); err != nil {
		return fmt.Errorf("copy agent: %w", err)
	}
	if serviceExists {
		if err := startService(); err != nil {
			return fmt.Errorf("restart existing service: %w", err)
		}
	} else if err := installService(dst); err != nil {
		return fmt.Errorf("install service: %w", err)
	}
	fmt.Printf("SentinelView Agent %s installed and enrolled as %s\n", version, cfg.AgentID)
	return nil
}

func enrollCommand(args []string) error {
	var cfg config
	if existing, err := loadConfig(); err == nil {
		cfg = existing
	}
	fs := flag.NewFlagSet("enroll", flag.ContinueOnError)
	server, token, site, tags := parseCommon(fs, &cfg)
	if err := fs.Parse(args); err != nil {
		return err
	}
	cfg.ServerURL = strings.TrimRight(*server, "/")
	cfg.Site = *site
	cfg.Tags = tagsFrom(*tags)
	if err := enroll(&cfg, *token); err != nil {
		return err
	}
	fmt.Printf("Enrolled as %s\n", cfg.AgentID)
	return nil
}

func diagnose() error {
	cfg, err := loadConfig()
	if err != nil {
		return fmt.Errorf("[FAIL] configuration: %w", err)
	}
	fmt.Println("[PASS] Configuration")
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, strings.TrimRight(cfg.ServerURL, "/")+"/healthz", nil)
	if err != nil {
		return err
	}
	resp, err := httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("[FAIL] Server connectivity: %w", err)
	}
	resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return fmt.Errorf("[FAIL] Server health: %s", resp.Status)
	}
	fmt.Println("[PASS] Server connectivity")
	c, cancel2 := context.WithTimeout(context.Background(), 10*time.Second)
	err = checkin(c, &cfg)
	cancel2()
	if err != nil {
		return fmt.Errorf("[FAIL] Agent credential/check-in: %w", err)
	}
	fmt.Println("[PASS] Agent credential and check-in")
	c, cancel3 := context.WithTimeout(context.Background(), 20*time.Second)
	err = sendTelemetry(c, cfg)
	cancel3()
	if err != nil {
		return fmt.Errorf("[FAIL] Telemetry: %w", err)
	}
	fmt.Println("[PASS] Telemetry upload")
	if _, err := cpu.Percent(200*time.Millisecond, false); err != nil {
		return fmt.Errorf("[FAIL] CPU collector: %w", err)
	}
	fmt.Println("[PASS] CPU collector")
	if _, err := mem.VirtualMemory(); err != nil {
		return fmt.Errorf("[FAIL] Memory collector: %w", err)
	}
	fmt.Println("[PASS] Memory collector")
	fmt.Println("Diagnosis complete: all critical checks passed")
	return nil
}

func usage() {
	fmt.Printf(`SentinelView Agent %s

Usage:
  sentinel-agent install --server URL --token TOKEN [--site SITE] [--tags a,b]
  sentinel-agent enroll  --server URL --token TOKEN [--site SITE] [--tags a,b]
  sentinel-agent run
  sentinel-agent status
  sentinel-agent start|stop|restart
  sentinel-agent diagnose
  sentinel-agent uninstall
  sentinel-agent version
`, version)
}

func main() {
	configureLogging()
	cmd := "run"
	args := []string{}
	if len(os.Args) > 1 {
		cmd = os.Args[1]
		args = os.Args[2:]
	}
	var err error
	switch cmd {
	case "version", "--version", "-v":
		fmt.Println(version)
		return
	case "install":
		err = installCommand(args)
	case "enroll":
		err = enrollCommand(args)
	case "run":
		var cfg config
		cfg, err = loadConfig()
		if err == nil {
			err = runAgent(context.Background(), cfg)
		}
	case "service":
		var cfg config
		cfg, err = loadConfig()
		if err == nil {
			err = runServiceMode(cfg)
		}
	case "start":
		err = startService()
	case "stop":
		err = stopService()
	case "restart":
		if e := stopService(); e != nil {
			log.Printf("stop: %v", e)
		}
		err = startService()
	case "status":
		var s string
		s, err = serviceStatus()
		if err == nil {
			fmt.Println(s)
		}
	case "uninstall":
		err = uninstallService()
	case "diagnose":
		err = diagnose()
	case "help", "--help", "-h":
		usage()
		return
	default:
		usage()
		err = fmt.Errorf("unknown command %q", cmd)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "Error:", err)
		os.Exit(1)
	}
}
