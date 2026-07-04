import { useEffect, useState } from "react";
import { api, type SessionStatus } from "../lib/api";
import { Card, Button, Select, StatChip } from "../components/ui";
import { ResultsTable } from "../components/ResultsTable";
import { AlertTriangle, Download } from "lucide-react";

interface DashboardProps {
  sessionId: string;
  status: SessionStatus;
  refresh: () => Promise<SessionStatus | null>;
}

export function Dashboard({ sessionId, status, refresh }: DashboardProps) {
  const [topN, setTopN] = useState("10");
  const [countries, setCountries] = useState<string[]>([]);
  const [cities, setCities] = useState<string[]>([]);
  const [zones, setZones] = useState<string[]>([]);

  const [selectedCountry, setSelectedCountry] = useState("");
  const [selectedCity, setSelectedCity] = useState("");
  const [selectedZone, setSelectedZone] = useState("");

  const [filterCountry, setFilterCountry] = useState("");
  const [filterCity, setFilterCity] = useState("");
  const [filterZone, setFilterZone] = useState("");
  const [companies, setCompanies] = useState<Record<string, unknown>[]>([]);
  const [counts, setCounts] = useState({ countries: 0, cities: 0, zones: 0, subareas: 0, leads: 0 });

  const a = status.agent_status;

  // Refresh counts whenever an agent finishes
  useEffect(() => {
    async function loadCounts() {
      const [countriesRes, citiesRes, zonesRes, subareasRes, companiesRes] = await Promise.all([
        api.getCountries(sessionId).catch(() => []),
        api.getCities(sessionId).catch(() => []),
        api.getZones(sessionId).catch(() => []),
        api.getSubareas(sessionId).catch(() => []),
        api.getCompanies(sessionId, {}).catch(() => []),
      ]);
      setCounts({
        countries: countriesRes.length,
        cities: citiesRes.length,
        zones: zonesRes.length,
        subareas: subareasRes.length,
        leads: companiesRes.length,
      });
    }
    loadCounts();
  }, [sessionId, a["1"], a["2"], a["3"], a["4"], a["5"]]);

  useEffect(() => {
    if (a["1"] === "Done") {
      api.getCountries(sessionId).then((rows) =>
        setCountries(rows.map((r) => r.country_name).filter((v): v is string => !!v))
      );
    }
  }, [sessionId, a["1"]]);

  useEffect(() => {
    if (a["2"] === "Done") {
      api.getCities(sessionId).then((rows) =>
        setCities([...new Set(rows.map((r) => r.city).filter((v): v is string => !!v))])
      );
    }
  }, [sessionId, a["2"]]);

  useEffect(() => {
    if (a["3"] === "Done") {
      api.getZones(sessionId).then((rows) =>
        setZones([...new Set(rows.map((r) => r.zone_name))])
      );
    }
  }, [sessionId, a["3"]]);

  // Cascading explorer options (uses the backend's dedicated endpoint)
  useEffect(() => {
    api
      .getExplorerOptions(sessionId, { country: filterCountry, city: filterCity, zone: filterZone })
      .catch(() => null);
  }, [sessionId, filterCountry, filterCity, filterZone]);

  useEffect(() => {
    api
      .getCompanies(sessionId, {
        country: filterCountry,
        city: filterCity,
        zone: filterZone,
      })
      .then(setCompanies)
      .catch(() => setCompanies([]));
  }, [sessionId, filterCountry, filterCity, filterZone, counts.leads]);

  async function handleRun1() {
    await api.runAgent1(sessionId, parseInt(topN, 10) || null);
    refresh();
  }
  async function handleRun2() {
    await api.runAgent2(sessionId, selectedCountry ? [selectedCountry] : []);
    refresh();
  }
  async function handleRun3() {
    await api.runAgent3(sessionId, selectedCity ? [selectedCity] : []);
    refresh();
  }
  async function handleRun4() {
    await api.runAgent4(sessionId, selectedZone ? [selectedZone] : []);
    refresh();
  }
  async function handleRun5() {
    await api.runAgent5(sessionId);
    refresh();
  }

  return (
    <div className="flex flex-col gap-5">
      {status.error && (
        <div className="flex items-start gap-3 bg-status-error/10 border border-status-error/30 text-status-error rounded-lg px-4 py-3">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <p className="text-sm">{status.error}</p>
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        <StatChip label="Countries" value={counts.countries} />
        <StatChip label="Cities" value={counts.cities} />
        <StatChip label="Zones" value={counts.zones} />
        <StatChip label="Sub-areas" value={counts.subareas} />
        <StatChip label="Leads" value={counts.leads} />
      </div>

      <Card title="Execute Pipeline">
        <div className="flex flex-col gap-4">
          {a["1"] === "Pending" && (
            <div className="flex items-end gap-3">
              <div className="flex-1 max-w-[200px]">
                <label className="block font-mono text-[10px] uppercase tracking-widest text-ink-500 mb-1.5">
                  Top N Countries
                </label>
                <input
                  value={topN}
                  onChange={(e) => setTopN(e.target.value)}
                  className="w-full bg-ink-850 border border-ink-700 rounded-lg px-3 py-2.5 text-sm text-ink-100 focus:border-signal-500"
                />
              </div>
              <Button onClick={handleRun1} disabled={status.running}>
                Run Agent 1
              </Button>
            </div>
          )}

          {a["1"] === "Done" && (a["2"] === "Pending" || a["2"] === "Error") && (
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <label className="block font-mono text-[10px] uppercase tracking-widest text-ink-500 mb-1.5">
                  Countries (blank = all {countries.length})
                </label>
                <Select
                  value={selectedCountry}
                  onChange={setSelectedCountry}
                  options={countries}
                  placeholder="All countries"
                />
              </div>
              <Button onClick={handleRun2} disabled={status.running}>
                Run Agent 2
              </Button>
            </div>
          )}

          {a["2"] === "Done" && (a["3"] === "Pending" || a["3"] === "Error") && (
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <label className="block font-mono text-[10px] uppercase tracking-widest text-ink-500 mb-1.5">
                  Cities (blank = all {cities.length})
                </label>
                <Select
                  value={selectedCity}
                  onChange={setSelectedCity}
                  options={cities}
                  placeholder="All cities"
                />
              </div>
              <Button onClick={handleRun3} disabled={status.running}>
                Run Agent 3
              </Button>
            </div>
          )}

          {a["3"] === "Done" && (a["4"] === "Pending" || a["4"] === "Error") && (
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <label className="block font-mono text-[10px] uppercase tracking-widest text-ink-500 mb-1.5">
                  Zones (blank = all {zones.length})
                </label>
                <Select
                  value={selectedZone}
                  onChange={setSelectedZone}
                  options={zones}
                  placeholder="All zones"
                />
              </div>
              <Button onClick={handleRun4} disabled={status.running}>
                Run Agent 4
              </Button>
            </div>
          )}

          {a["4"] === "Done" && (a["5"] === "Pending" || a["5"] === "Error") && (
            <div className="flex items-center gap-3">
              <p className="text-sm text-ink-300 flex-1">
                Ready to scrape leads for the selected sub-areas.
              </p>
              <Button onClick={handleRun5} disabled={status.running}>
                Run Agent 5 — Scraper
              </Button>
            </div>
          )}

          {a["5"] === "Done" && (
            <div className="flex items-center gap-3">
              <p className="text-sm text-status-done font-medium flex-1">
                Pipeline completed.
              </p>
              {status.output_file && (
                <a href={api.downloadUrl(sessionId)} download>
                  <Button variant="secondary">
                    <Download className="w-3.5 h-3.5" />
                    Download results
                  </Button>
                </a>
              )}
            </div>
          )}

          {status.running && (
            <p className="text-sm text-signal-400 font-mono">
              ● Agent running in the background — status updates automatically.
            </p>
          )}

          {!status.running && (
            <div className="pt-2 border-t border-ink-800">
              <Button
                variant="ghost"
                onClick={async () => {
                  await api.resetSession(sessionId);
                  refresh();
                }}
              >
                Reset pipeline state
              </Button>
            </div>
          )}
        </div>
      </Card>

      <Card title="Data Explorer">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Select
            value={filterCountry}
            onChange={setFilterCountry}
            options={countries}
            placeholder="Filter by country"
          />
          <Select
            value={filterCity}
            onChange={setFilterCity}
            options={cities}
            placeholder="Filter by city"
          />
          <Select
            value={filterZone}
            onChange={setFilterZone}
            options={zones}
            placeholder="Filter by zone"
          />
        </div>
      </Card>

      <Card title="Resultant Company Data">
        <ResultsTable rows={companies} />
      </Card>
    </div>
  );
}
