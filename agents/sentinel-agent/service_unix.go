//go:build !windows

package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"runtime"
)

func runServiceMode(cfg config) error { return runAgent(context.Background(), cfg) }

func installService(exePath string) error {
	if runtime.GOOS != "linux" {
		return fmt.Errorf("service installation is currently supported on Windows and systemd Linux")
	}
	unit := `[Unit]
Description=SentinelView Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=` + exePath + ` service
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
`
	if err := os.WriteFile("/etc/systemd/system/sentinel-agent.service", []byte(unit), 0644); err != nil {
		return err
	}
	if out, err := exec.Command("systemctl", "daemon-reload").CombinedOutput(); err != nil {
		return fmt.Errorf("systemctl daemon-reload: %v: %s", err, string(out))
	}
	if out, err := exec.Command("systemctl", "enable", "--now", "sentinel-agent.service").CombinedOutput(); err != nil {
		return fmt.Errorf("systemctl enable: %v: %s", err, string(out))
	}
	return nil
}
func systemctl(args ...string) error {
	out, err := exec.Command("systemctl", args...).CombinedOutput()
	if err != nil {
		return fmt.Errorf("systemctl %v: %v: %s", args, err, string(out))
	}
	return nil
}
func startService() error { return systemctl("start", "sentinel-agent.service") }
func stopService() error  { return systemctl("stop", "sentinel-agent.service") }
func uninstallService() error {
	_ = systemctl("disable", "--now", "sentinel-agent.service")
	_ = os.Remove("/etc/systemd/system/sentinel-agent.service")
	_ = exec.Command("systemctl", "daemon-reload").Run()
	return nil
}
func serviceStatus() (string, error) {
	out, err := exec.Command("systemctl", "is-active", "sentinel-agent.service").CombinedOutput()
	return string(out), err
}
