package main

import (
	"encoding/json"
	"reflect"
	"testing"
)

func TestTagsFrom(t *testing.T) {
	got := tagsFrom(" windows, production ,,database ")
	want := []string{"windows", "production", "database"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("tagsFrom() = %#v, want %#v", got, want)
	}
}

func TestPolicyReaders(t *testing.T) {
	cfg := config{Policy: map[string]any{
		"collect_cpu":                false,
		"telemetry_interval_seconds": float64(15),
		"checkin_interval_seconds":   json.Number("30"),
	}}

	if boolPolicy(cfg, "collect_cpu", true) {
		t.Fatal("expected collect_cpu=false")
	}
	if !boolPolicy(cfg, "missing_bool", true) {
		t.Fatal("expected missing boolean to use default")
	}
	if got := intPolicy(cfg, "telemetry_interval_seconds", 60); got != 15 {
		t.Fatalf("telemetry interval = %d, want 15", got)
	}
	if got := intPolicy(cfg, "checkin_interval_seconds", 60); got != 30 {
		t.Fatalf("checkin interval = %d, want 30", got)
	}
	if got := intPolicy(cfg, "missing_int", 60); got != 60 {
		t.Fatalf("missing interval = %d, want default 60", got)
	}
}

func TestConfigPathOverride(t *testing.T) {
	t.Setenv("SENTINEL_CONFIG", "/tmp/sentinel-agent-test.json")
	if got := defaultConfigPath(); got != "/tmp/sentinel-agent-test.json" {
		t.Fatalf("defaultConfigPath() = %q", got)
	}
}
