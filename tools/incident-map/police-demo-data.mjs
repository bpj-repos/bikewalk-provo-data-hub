import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import { validateDetails } from "./combined-demo-data.mjs";

export const policeModes = new Set([
  "bicycle",
  "electric-bicycle",
  "scooter",
  "skateboard",
  "unknown-electric-micromobility",
  "other-micromobility",
  "mobility-device",
  "pedestrian-and-scooter",
  "pedestrian",
  "bicycle-and-pedestrian",
]);

export function validatePrepared(prepared, summary) {
  const exact = (value, keys) => assert.deepEqual(Object.keys(value).sort(), [...keys].sort());
  const strings = (values, allowed) => {
    assert.ok(Array.isArray(values));
    for (const value of values) {
      assert.ok(typeof value === "string" && value.length <= 16000);
      if (allowed) assert.ok(allowed.includes(value), `Unknown prepared category: ${value}`);
    }
  };
  exact(prepared, ["version", "filters", "overview"]);
  assert.equal(prepared.version, 1);
  const f = prepared.filters;
  exact(f, ["years", "modeGroups", "fineModes", "crashSeverity", "atSeverity", "factors", "lighting", "sources"]);
  strings(f.years); f.years.forEach((year) => assert.match(year, /^20[0-9]{2}$/));
  strings(f.modeGroups, ["walking", "bicycle", "other"]);
  strings(f.fineModes, ["pedestrian", "bicycle", "electric-bicycle", "scooter", "skateboard", "mobility-device", "other-conveyance", "unspecified-electric-micromobility"]);
  strings(f.crashSeverity, ["fatal", "serious", "other", "unknown"]);
  assert.ok(["serious-fatal", "other", "unknown"].includes(f.atSeverity));
  strings(f.factors, ["speeding", "distraction", "drowsiness", "dui", "aggressive-driving", "disregarded-control", "wrong-way", "hit-and-run", "alcohol-confirmed", "alcohol-suspected", "drugs-confirmed", "drugs-suspected", "failure-to-yield"]);
  strings(f.lighting, ["daylight", "dawn-dusk", "dark", "unknown"]);
  strings(f.sources, ["provo-police-incidents", "udot-crashes", "utah-crash-portal"]);
  const o = prepared.overview;
  exact(o, ["locationLabels", "dates", "atInjuries", "crashSeverity", "circumstances", "modeConflict", "atInjuryAvailability", "timeNotes"]);
  for (const key of ["locationLabels", "atInjuries", "crashSeverity", "circumstances", "atInjuryAvailability", "timeNotes"]) strings(o[key]);
  assert.equal(typeof o.modeConflict, "boolean");
  assert.ok(Array.isArray(o.dates));
  for (const d of o.dates) { exact(d, ["label", "text"]); assert.ok(["Crash date", "Police report date"].includes(d.label)); assert.match(d.text, /^20[0-9]{2}-[0-9]{2}-[0-9]{2}$/); }
  assert.ok(Array.isArray(summary));
  for (const section of summary) {
    exact(section, ["heading", "entries"]);
    assert.match(section.heading, /^(Identity|When|Location|Transportation|Outcomes|Circumstances|Person [1-9][0-9]*|Vehicle [1-9][0-9]*)$/);
    assert.ok(Array.isArray(section.entries));
    for (const entry of section.entries) {
      exact(entry, ["key", "label", "values"]);
      assert.match(entry.key, /^(identity|agency|time|road|location|travel|vehicle|person|injury|count|classification|condition|event)\.[a-z_]+$/);
      assert.notEqual(entry.key, "location.point", "Do not expose full-precision normalized coordinates");
      strings([entry.label]); assert.ok(Array.isArray(entry.values));
      for (const value of entry.values) { exact(value, ["text", "sources"]); strings([value.text]); strings(value.sources); }
    }
  }
}

export function validateDemoLayer(layer) {
  assert.deepEqual(Object.keys(layer).sort(), ["features", "type"]);
  assert.equal(layer.type, "FeatureCollection");
  assert.ok(Array.isArray(layer.features));
  for (const f of layer.features) {
    assert.deepEqual(Object.keys(f).sort(), ["geometry", "properties", "type"]);
    assert.equal(f.type, "Feature");
    assert.deepEqual(Object.keys(f.geometry).sort(), ["coordinates", "type"]);
    assert.equal(f.geometry.type, "Point");
    const extras = ["summary", "prepared"].filter((key) => key in f.properties);
    assert.deepEqual(Object.keys(f.properties).sort(), (f.properties.details ? ["details", "mode", "month", "source", ...extras] : ["mode", "month", ...extras]).sort());
    assert.equal(Boolean(f.properties.summary), Boolean(f.properties.prepared));
    if (f.properties.prepared) validatePrepared(f.properties.prepared, f.properties.summary);
    if (f.properties.details) {
      assert.ok(["Provo Police", "UDOT", "Provo Police + UDOT"].includes(f.properties.source));
      validateDetails(f.properties.details);
    }
    assert.ok(policeModes.has(f.properties.mode));
    assert.match(f.properties.month, /^20\d{2}-(0[1-9]|1[0-2])$/);
    const [lng, lat] = f.geometry.coordinates;
    assert.ok(f.geometry.coordinates.every((c) => Number.isFinite(c) && Number(c.toFixed(4)) === c), "Coordinates must retain approved four-decimal precision");
    assert.equal(f.geometry.coordinates.length, 2);
    assert.ok(Number.isFinite(lng) && lng >= -111.75 && lng <= -111.55);
    assert.ok(Number.isFinite(lat) && lat >= 40.18 && lat <= 40.35);
  }
}

export function validateDemoRelease(
  directory = "public/data/demos/police-incidents",
) {
  const m = JSON.parse(readFileSync(path.join(directory, "manifest.json")));
  const extraKeys = ["combinedSnapshotId", "possibleMatchCount", "sourceCoverage", "normalization"].filter((key) => key in m);
  assert.deepEqual(Object.keys(m).sort(), [
    "approval",
    "fromMonth",
    "mappedCount",
    "omittedCount",
    "producerCommit",
    "recordCount",
    "releaseId",
    "sha256",
    "source",
    "sourceCurrentThrough",
    "toMonth",
    ...extraKeys,
  ].sort());
  assert.ok(m.approval && m.releaseId);
  assert.ok(["Provo Police Department active transportation incident workbooks", "Provo Police workbooks and UDOT public Crash Locations", "Provo Police, UDOT and Utah DPS Crash Data Portal"].includes(m.source));
  if (m.sourceCoverage) {
    assert.match(m.combinedSnapshotId, /^combined-incidents-[a-f0-9]{16}$/);
    assert.ok(Number.isInteger(m.possibleMatchCount) && m.possibleMatchCount >= 0);
    assert.ok(m.sourceCoverage.length >= 2 && m.sourceCoverage.length <= 3);
    for (const s of m.sourceCoverage) {
      assert.deepEqual(Object.keys(s).sort(), ["checkedAt", "records", "snapshotId", "sourceCurrentThrough", "sourceKey", "warnings"]);
      assert.ok(["udot-crashes", "provo-police-incidents", "utah-crash-portal"].includes(s.sourceKey));
      assert.ok(Number.isInteger(s.records) && s.records >= 0);
    }
  }
  if (m.normalization) {
    assert.deepEqual(Object.keys(m.normalization).sort(), ["baseLayerSha256", "baseReleaseId", "catalogSha256", "contractSha256", "derivedManifestSha256", "derivedRulesSha256", "normalizedManifestSha256"].sort());
    for (const [key, value] of Object.entries(m.normalization)) if (key !== "baseReleaseId") assert.match(value, /^[a-f0-9]{64}$/);
  }
  assert.match(m.producerCommit, /^[a-f0-9]{40}$/);
  const data = readFileSync(path.join(directory, "incidents.json"));
  assert.equal(createHash("sha256").update(data).digest("hex"), m.sha256);
  const layer = JSON.parse(data);
  validateDemoLayer(layer);
  if (m.normalization) assert.ok(layer.features.every((f) => f.properties.prepared?.version === 1));
  assert.ok(Number.isInteger(m.recordCount) && m.recordCount >= 0);
  assert.ok(Number.isInteger(m.omittedCount) && m.omittedCount >= 0);
  assert.equal(layer.features.length, m.mappedCount);
  assert.equal(m.mappedCount + m.omittedCount, m.recordCount);
  const months = layer.features.map((f) => f.properties.month).sort();
  assert.equal(m.fromMonth, months[0]);
  assert.equal(m.toMonth, months.at(-1));
  assert.match(m.sourceCurrentThrough, /^20\d{2}-(0[1-9]|1[0-2])$/);
  return m;
}
