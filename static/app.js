const globeElement = document.getElementById('globeViz');
const focusElement = document.getElementById('continentFocus');
const focusName = focusElement.querySelector('.focus-name');
const globeShell = document.querySelector('.globe-shell');

const world = new Globe(globeElement)
  .globeImageUrl('//cdn.jsdelivr.net/npm/three-globe/example/img/earth-blue-marble.jpg')
  .bumpImageUrl('//cdn.jsdelivr.net/npm/three-globe/example/img/earth-topology.png')
  .backgroundColor('rgba(0,0,0,0)');

world.controls().autoRotate = true;
world.controls().autoRotateSpeed = 2.2;
world.controls().enableZoom = false;
world.controls().enablePan = false;

function resizeGlobe() {
  const rect = globeElement.getBoundingClientRect();
  world.width(rect.width);
  world.height(rect.height);
}

resizeGlobe();
window.addEventListener('resize', resizeGlobe);

const colors = {
  Africa: 'rgba(218,130,92,0.36)',
  Asia: 'rgba(126,142,226,0.36)',
  Europe: 'rgba(106,196,210,0.36)',
  'North America': 'rgba(118,184,142,0.36)',
  'South America': 'rgba(212,176,86,0.36)',
  Oceania: 'rgba(176,136,214,0.36)',
  Antarctica: 'rgba(190,214,226,0.32)'
};

const hoverColors = {
  Africa: 'rgba(236,154,116,0.84)',
  Asia: 'rgba(150,164,244,0.84)',
  Europe: 'rgba(126,220,226,0.84)',
  'North America': 'rgba(139,210,164,0.84)',
  'South America': 'rgba(230,196,106,0.84)',
  Oceania: 'rgba(198,158,232,0.84)',
  Antarctica: 'rgba(214,232,238,0.78)'
};

const accentColors = {
  Africa: '#ec9a74',
  Asia: '#96a4f4',
  Europe: '#7edce2',
  'North America': '#8bd2a4',
  'South America': '#e6c46a',
  Oceania: '#c69ee8',
  Antarctica: '#d6e8ee'
};

const continentCenters = {
  Africa: { lat: 3, lng: 20, altitude: 1.62 },
  Asia: { lat: 34, lng: 92, altitude: 1.76 },
  Europe: { lat: 51, lng: 14, altitude: 1.58 },
  'North America': { lat: 48, lng: -104, altitude: 1.66 },
  'South America': { lat: -18, lng: -61, altitude: 1.62 },
  Oceania: { lat: -24, lng: 135, altitude: 1.72 },
  Antarctica: { lat: -78, lng: 15, altitude: 1.9 }
};

const norm = s => s?.toLowerCase().trim();

const alias = {
  "united states of america": "united states",
  "usa": "united states",
  "u.s.a.": "united states",
  "u.s.": "united states",
  "england": "united kingdom",
  "uk": "united kingdom",
  "u.k.": "united kingdom",
  "great britain": "united kingdom",
  "russian federation": "russia",
  "republic of serbia": "serbia",
  "czech republic": "czechia",
  "czech rep.": "czechia",
  "cote d'ivoire": "ivory coast",
  "côte d'ivoire": "ivory coast",
  "congo (kinshasa)": "democratic republic of the congo",
  "congo (brazzaville)": "republic of the congo",
  "republic of the congo": "congo",
  "democratic republic of the congo": "democratic republic of congo",
  "dem. rep. congo": "democratic republic of congo",
  "burkina faso": "burkina",
  "united republic of tanzania": "tanzania",
  "tanzania, united republic of": "tanzania",
  "myanmar": "burma (myanmar)",
  "myanmarr": "burma (myanmar)"
};

function resolveCountryName(rawName) {
  const name = norm(rawName);
  if (!name) return null;
  if (continentMap[name]) return name;

  const aliasName = alias[name];
  if (aliasName && continentMap[aliasName]) return aliasName;

  return name;
}

function continentToPath(continent) {
  return `/${continent.toLowerCase().replace(/\s+/g, '-')}`;
}

let continentMap = {};
let activeContinent = null;

function setSpin(isSpinning) {
  world.controls().autoRotate = isSpinning;
}

fetch(globeElement.dataset.csvUrl)
  .then(r => r.text())
  .then(text => {
    const rows = text.split('\n').slice(1);
    rows.forEach(row => {
      const [continent, country] = row.split(',');
      if (!country || !continent) return;
      continentMap[norm(country)] = continent.trim();
    });

    continentMap.antarctica = 'Antarctica';

    init();
  });

function setActiveContinent(continent) {
  if (activeContinent === continent) return;
  activeContinent = continent;

  if (continent) {
    focusName.textContent = continent;
    focusElement.classList.add('is-visible');
    globeShell.classList.add('is-focused');
    globeElement.classList.add('is-clickable');
    document.documentElement.style.setProperty('--focus-accent', accentColors[continent] || '#d7dee8');
    setSpin(false);
    world.pointOfView(continentCenters[continent] || { lat: 52, lng: -95, altitude: 1.72 }, 850);
  } else {
    focusName.textContent = 'Choose a continent';
    // keep the focus element visible so the default prompt is always shown
    focusElement.classList.add('is-visible');
    globeShell.classList.remove('is-focused');
    globeElement.classList.remove('is-clickable');
    document.documentElement.style.setProperty('--focus-accent', '#d7dee8');
    setSpin(true);
  }

  world
    .polygonCapColor(world.polygonCapColor())
    .polygonAltitude(world.polygonAltitude())
    .polygonStrokeColor(world.polygonStrokeColor());
}

function init() {
  fetch('https://raw.githubusercontent.com/holtzy/D3-graph-gallery/master/DATA/world.geojson')
    .then(r => r.json())
    .then(countries => {
      world
        .polygonsData(countries.features)
        .polygonsTransitionDuration(520)
        .polygonCapColor(d => {
          const name = resolveCountryName(d.properties.name);
          const cont = continentMap[name];

          if (!activeContinent) return colors[cont] || 'rgba(96,104,116,0.20)';

          return cont === activeContinent
            ? (hoverColors[cont] || 'rgba(140,150,165,0.70)')
            : 'rgba(16,20,26,0.045)';
        })
        .polygonAltitude(d => {
          const name = resolveCountryName(d.properties.name);
          const cont = continentMap[name];
          if (!activeContinent) return 0.008;
          return cont === activeContinent ? 0.072 : 0.0015;
        })
        .polygonSideColor(d => {
          const name = resolveCountryName(d.properties.name);
          const cont = continentMap[name];
          return cont === activeContinent ? 'rgba(255,255,255,0.10)' : 'rgba(0,0,0,0)';
        })
        .polygonStrokeColor(d => {
          const name = resolveCountryName(d.properties.name);
          const cont = continentMap[name];
          return cont === activeContinent ? 'rgba(255,255,255,0.34)' : 'rgba(255,255,255,0.025)';
        })
        .polygonLabel(d => {
          const name = resolveCountryName(d.properties.name);
          const cont = continentMap[name];
          if (!cont) return d.properties.name;
          return `<span>${cont}</span>`;
        });

      world.onPolygonHover(d => {
        if (!d) {
          setActiveContinent(null);
          return;
        }

        const name = resolveCountryName(d.properties.name);
        setActiveContinent(continentMap[name] || null);
      });

      world.onPolygonClick(d => {
        if (!d) return;
        const name = resolveCountryName(d.properties.name);
        const cont = continentMap[name];
        if (!cont) return;
        window.location.href = continentToPath(cont);
      });
    });
}

world.pointOfView({ lat: 52, lng: -95, altitude: 1.72 });
// show the default focus message on load
setActiveContinent(null);
