//go:build windows

package main

import (
	"context"
	"fmt"
	"time"

	"golang.org/x/sys/windows/svc"
	"golang.org/x/sys/windows/svc/mgr"
)

type serviceHandler struct{ cfg config }

func (h *serviceHandler) Execute(_ []string, requests <-chan svc.ChangeRequest, changes chan<- svc.Status) (bool, uint32) {
	const accepts = svc.AcceptStop | svc.AcceptShutdown
	changes <- svc.Status{State: svc.StartPending}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- runAgent(ctx, h.cfg) }()
	changes <- svc.Status{State: svc.Running, Accepts: accepts}
	for {
		select {
		case err := <-done:
			if err != nil {
				return false, 1
			}
			return false, 0
		case req := <-requests:
			switch req.Cmd {
			case svc.Interrogate:
				changes <- req.CurrentStatus
			case svc.Stop, svc.Shutdown:
				changes <- svc.Status{State: svc.StopPending}
				cancel()
				select {
				case <-done:
				case <-time.After(20 * time.Second):
				}
				return false, 0
			}
		}
	}
}

func runServiceMode(cfg config) error { return svc.Run(serviceName, &serviceHandler{cfg: cfg}) }

func installService(exePath string) error {
	m, err := mgr.Connect()
	if err != nil {
		return err
	}
	defer m.Disconnect()
	if existing, err := m.OpenService(serviceName); err == nil {
		existing.Close()
		return fmt.Errorf("service %s already exists", serviceName)
	}
	s, err := m.CreateService(serviceName, exePath, mgr.Config{DisplayName: "SentinelView Agent", StartType: mgr.StartAutomatic}, "service")
	if err != nil {
		return err
	}
	defer s.Close()
	if err := s.Start(); err != nil {
		_ = s.Delete()
		return err
	}
	return nil
}

func startService() error {
	m, e := mgr.Connect()
	if e != nil {
		return e
	}
	defer m.Disconnect()
	s, e := m.OpenService(serviceName)
	if e != nil {
		return e
	}
	defer s.Close()
	return s.Start()
}
func stopService() error {
	m, e := mgr.Connect()
	if e != nil {
		return e
	}
	defer m.Disconnect()
	s, e := m.OpenService(serviceName)
	if e != nil {
		return e
	}
	defer s.Close()
	_, e = s.Control(svc.Stop)
	if e != nil {
		return e
	}
	for i := 0; i < 30; i++ {
		q, _ := s.Query()
		if q.State == svc.Stopped {
			return nil
		}
		time.Sleep(time.Second)
	}
	return fmt.Errorf("service did not stop")
}
func uninstallService() error {
	_ = stopService()
	m, e := mgr.Connect()
	if e != nil {
		return e
	}
	defer m.Disconnect()
	s, e := m.OpenService(serviceName)
	if e != nil {
		return e
	}
	defer s.Close()
	return s.Delete()
}
func serviceStatus() (string, error) {
	m, e := mgr.Connect()
	if e != nil {
		return "", e
	}
	defer m.Disconnect()
	s, e := m.OpenService(serviceName)
	if e != nil {
		return "", e
	}
	defer s.Close()
	q, e := s.Query()
	if e != nil {
		return "", e
	}
	return fmt.Sprintf("SentinelView Agent service state: %v", q.State), nil
}
