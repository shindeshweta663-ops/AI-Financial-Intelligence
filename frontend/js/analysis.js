const $ = (s, r = document) => r.querySelector(s),
  $$ = (s, r = document) => [...r.querySelectorAll(s)];
const rng = (s) => () => {
  s |= 0;
  s = (s + 0x6d2b79f5) | 0;
  let t = Math.imul(s ^ (s >>> 15), 1 | s);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};
const gen = (seed, n, v, vol, dr) => {
  const r = rng(seed),
    a = [];
  for (let i = 0; i < n; i++) {
    v *= 1 + dr + (r() - 0.5) * vol;
    a.push(v);
  }
  return a;
};
const f2 = (n) =>
    n.toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }),
  f0 = (n) => n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
// Financial colour semantics: green = up, red = down, gray = unchanged
const cls = (n, d = 2) =>
    Math.abs(n) < 0.5 * 10 ** -d ? "flat" : n > 0 ? "up" : "down",
  pc = (n, d = 2) => {
    if (Math.abs(n) < 0.5 * 10 ** -d) n = 0;
    return (n > 0 ? "+" : "") + n.toFixed(d) + "%";
  };
const cr = (n) =>
  n >= 1e5 ? "₹" + (n / 1e5).toFixed(2) + " L Cr" : "₹" + f0(n) + " Cr";
const mean = (a) => a.reduce((x, y) => x + y, 0) / a.length,
  sd = (a) => {
    const m = mean(a);
    return Math.sqrt(mean(a.map((v) => (v - m) ** 2)));
  };

const ST = {
  RELIANCE: {
    n: "Reliance Industries",
    sec: "Energy",
    s: 3,
    p: 2400,
    v: 0.022,
    d: 0.0006,
    q: 232000,
    m: 0.078,
    eps: 26.6,
    pe: 24.1,
    beta: 1.05,
  },
  TCS: {
    n: "Tata Consultancy Services",
    sec: "IT",
    s: 8,
    p: 3600,
    v: 0.018,
    d: 0.0003,
    q: 63000,
    m: 0.19,
    eps: 34,
    pe: 28.3,
    beta: 0.78,
  },
  INFY: {
    n: "Infosys",
    sec: "IT",
    s: 5,
    p: 1500,
    v: 0.024,
    d: -0.0002,
    q: 40500,
    m: 0.16,
    eps: 17.5,
    pe: 23.9,
    beta: 0.85,
  },
  HDFCBANK: {
    n: "HDFC Bank",
    sec: "Banking",
    s: 11,
    p: 1650,
    v: 0.016,
    d: 0.0004,
    q: 88000,
    m: 0.21,
    eps: 21.2,
    pe: 18.6,
    beta: 0.95,
  },
  ICICIBANK: {
    n: "ICICI Bank",
    sec: "Banking",
    s: 17,
    p: 1180,
    v: 0.017,
    d: 0.0005,
    q: 52000,
    m: 0.27,
    eps: 17.4,
    pe: 17.2,
    beta: 1,
  },
  SUNPHARMA: {
    n: "Sun Pharmaceutical",
    sec: "Pharma",
    s: 23,
    p: 1700,
    v: 0.019,
    d: 0.0003,
    q: 13500,
    m: 0.22,
    eps: 41,
    pe: 34,
    beta: 0.7,
  },
};

const SECS = [
  ["Banking", 3.2],
  ["IT", -1.4],
  ["Energy", 2.1],
  ["Pharma", 0.8],
  ["Auto", -0.6],
  ["FMCG", 1.1],
];

const DATES = (() => {
  const a = [],
    d = new Date(2026, 9, 6);
  while (a.length < 252) {
    if (d.getDay() % 6) a.unshift(new Date(d));
    d.setDate(d.getDate() - 1);
  }
  return a;
})();

const fd = (d) =>
  d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
const fdl = (d) =>
  d.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });

const ema = (a, n) => {
  const k = 2 / (n + 1);
  let e = a[0];
  return a.map((v) => (e = v * k + e * (1 - k)));
};

const bb = (a) => {
  const u = [],
    l = [],
    m = [];

  a.forEach((_, i) => {
    if (i < 19) {
      u.push(null);
      l.push(null);
      m.push(null);
    } else {
      const w = a.slice(i - 19, i + 1),
        mu = mean(w),
        s = sd(w);

      m.push(mu);
      u.push(mu + 2 * s);
      l.push(mu - 2 * s);
    }
  });

  return { u, l, m };
};

const rsi = (a) => {
  let g = 0,
    l = 0;

  for (let i = 1; i <= 14; i++) {
    const c = a[i] - a[i - 1];
    c > 0 ? (g += c) : (l -= c);
  }

  g /= 14;
  l /= 14;

  for (let i = 15; i < a.length; i++) {
    const c = a[i] - a[i - 1];

    g = (g * 13 + Math.max(c, 0)) / 14;
    l = (l * 13 + Math.max(-c, 0)) / 14;
  }

  return 100 - 100 / (1 + g / (l || 1e-9));
};

const rets = (a) => a.map((v, i) => (i ? Math.log(v / a[i - 1]) : 0)).slice(1);

function forecast(d, n) {
  const l = d[d.length - 1],
    r = rets(d.slice(-30)),
    m = mean(r),
    s = sd(r),
    mid = [],
    hi = [],
    lo = [];

  for (let i = 1; i <= n; i++) {
    const c = l * Math.exp(m * i * 0.8),
      w = s * Math.sqrt(i) * 1.4;

    mid.push(c);
    hi.push(c * Math.exp(w));
    lo.push(c * Math.exp(-w));
  }

  return { mid, hi, lo };
}

// Chart colours are read from the CSS variables so the palette lives in one place
const COL = (() => {
  const s = getComputedStyle(document.documentElement),
    g = (n) => s.getPropertyValue(n).trim();
  return { up: g("--up"), down: g("--down"), flat: g("--flat") };
})();

let K = "RELIANCE",
  D,
  A,
  rg = 126,
  first = true;

function analyze(k) {
  K = k;

  const s = ST[k],
    d = gen(s.s, 252, s.p, s.v * 2.2, s.d),
    e20 = ema(d, 20),
    e50 = ema(d, 50),
    m12 = ema(d, 12),
    m26 = ema(d, 26),
    mc = m12.map((v, i) => v - m26[i]),
    sg = ema(mc, 9),
    B = bb(d),
    R = rsi(d),
    L = d.length - 1,
    r = rets(d),
    vol = sd(r.slice(-60)) * Math.sqrt(252) * 100;

  let pk = d[0],
    dd = 0;

  d.forEach((v) => {
    pk = Math.max(pk, v);
    dd = Math.min(dd, v / pk - 1);
  });

  const hist = mc[L] - sg[L],
    score = Math.max(
      5,
      Math.min(
        95,
        50 +
          (R - 50) * 0.4 +
          (hist > 0 ? 15 : -15) +
          (d[L] > e50[L] ? 15 : -15),
      ),
    ),
    sent = score >= 62 ? "Bullish" : score <= 38 ? "Bearish" : "Neutral",
    risk = vol < 18 ? 0 : vol < 22 ? 1 : 2,
    ret = (n) => (d[L] / d[L - n] - 1) * 100,
    fc = forecast(d, 30),
    exp = (fc.mid[29] / d[L] - 1) * 100;

  A = {
    s,
    d,
    e20,
    e50,
    mc,
    sg,
    B,
    R,
    L,
    vol,
    dd: dd * 100,
    hist,
    score,
    sent,
    risk,
    ret,
    fc,
    exp,
    ch: (d[L] / d[L - 1] - 1) * 100,
    chA: d[L] - d[L - 1],
    var95: 1.65 * sd(r.slice(-60)) * 100,

    trend: exp > 1 ? "Upward" : exp < -1 ? "Downward" : "Sideways",
    fdir: cls(exp),

    fin: {
      rev: [0, 1, 2, 3].map((i) => Math.round(s.q * (1 - 0.015 * i))),

      eps: [0, 1, 2, 3].map((i) => s.eps * (1 - 0.02 * i)),
    },
  };

  A.fin.np = A.fin.rev.map((v) => Math.round(v * s.m));

  render();
}

function render() {
  const a = A,
    s = a.s,
    rl = ["Low", "Moderate", "High"][a.risk];

  $("#q").value = s.n;
  $("#sel").value = K;
  $("#ct").textContent = `${K} · Price Chart`;

  const card = (i, l, v, sub, x = "") =>
    `<div class="gc ov" style="--i:${i}">
            <small>${l}</small>
            <div class="v">${v}</div>
            <div class="s">${sub}</div>
            ${x}
        </div>`;

  $("#overview").innerHTML =
    card(
      0,
      "Current Price",
      `<span data-c="${a.d[a.L]}" data-d="2" data-p="₹"></span>`,
      `${s.n} · close ${fdl(DATES[a.L])}`,
    ) +
    card(
      1,
      "Daily Change",
      `<span class="${cls(a.ch)}">
                <i class="bi bi-caret-${a.ch >= 0 ? "up" : "down"}-fill"></i>
                <span
                    data-c="${a.ch}"
                    data-d="2"
                    data-s="%"
                    data-sg="1">
                </span>
            </span>`,
      `<span class="${cls(a.chA)}">
                ${a.chA >= 0 ? "+" : "-"}₹${f2(Math.abs(a.chA))}
            </span> vs previous close`,
    ) +
    card(
      2,
      "RSI (14)",
      `<span data-c="${a.R}" data-d="1"></span>`,
      a.R > 70
        ? "Overbought zone"
        : a.R < 30
          ? "Oversold zone"
          : "Neutral zone",

      `<div class="bar zone">
                <span class="mk" style="left:${a.R}%"></span>
            </div>`,
    ) +
    card(
      3,
      "Market Sentiment",
      `<span class="${
        a.sent == "Bullish" ? "up" : a.sent == "Bearish" ? "down" : "flat"
      }">${a.sent}</span>`,
      `Composite score ${Math.round(a.score)}/100`,

      `<div
                class="bar zone"
                style="transform:scaleX(-1)">
                <span
                    class="mk"
                    style="left:${100 - a.score}%">
                </span>
            </div>`,
    ) +
    card(
      4,
      "Risk Level",
      `<span class="${["up", "flat", "down"][a.risk]}">
                ${rl}
            </span>`,
      `Annualised volatility ${a.vol.toFixed(1)}%`,

      `<div class="seg">
                ${[0, 1, 2]
                  .map(
                    (i) =>
                      `<i style="${
                        i <= a.risk
                          ? "background:" +
                            ["var(--up)", "var(--flat)", "var(--down)"][a.risk]
                          : ""
                      }"></i>`,
                  )
                  .join("")}
            </div>`,
    );

  counters();
  chartMain();

  const sig = (t, c) => `<span class="badge2 ${c}">${t}</span>`;

  const L = a.L;

  $("#ti").innerHTML = `

        <div class="ind">

            <b>RSI (14)</b>

            <span class="val">

                ${a.R.toFixed(1)}

                ${
                  a.R > 70
                    ? sig("Overbought", "b-n")
                    : a.R < 30
                      ? sig("Oversold", "b-p")
                      : sig("Neutral", "b-m")
                }

            </span>

            <div class="bar zone">

                <span
                    class="mk"
                    style="left:${a.R}%">
                </span>

            </div>

        </div>


        <div class="ind">

            <b>MACD (12,26,9)</b>

            <span class="val">

                ${a.mc[L].toFixed(2)}

                ${a.hist > 0 ? sig("Bullish", "b-p") : sig("Bearish", "b-n")}

            </span>

            <small class="mute">

                Signal ${a.sg[L].toFixed(2)}
                · Hist

                <span class="${cls(a.hist)}">
                    ${a.hist.toFixed(2)}
                </span>

            </small>

            <span></span>

        </div>


        <div class="ind">

            <b>EMA 20 / 50</b>

            <span class="val">
                ${f2(a.e20[L])} /
                ${f2(a.e50[L])}
            </span>

            <small class="mute">
                Price vs EMA 50
            </small>

            <span class="val ${cls(a.d[L] - a.e50[L])}">
                ${pc((a.d[L] / a.e50[L] - 1) * 100)}
            </span>

        </div>


        <div class="ind">

            <b>Bollinger Bands (20,2)</b>

            <span class="val">

                ${
                  a.d[L] > a.B.u[L]
                    ? sig("Above band", "b-n")
                    : a.d[L] < a.B.l[L]
                      ? sig("Below band", "b-p")
                      : sig("Inside band", "b-m")
                }

            </span>

            <small class="mute">

                ${f2(a.B.l[L])}
                –
                ${f2(a.B.u[L])}

            </small>

            <span class="val">

                %B ${(
                  ((a.d[L] - a.B.l[L]) / (a.B.u[L] - a.B.l[L])) *
                  100
                ).toFixed(0)}

            </span>

            <div class="bar">

                <b
                    style="
                        width:${Math.max(
                          0,
                          Math.min(
                            100,
                            ((a.d[L] - a.B.l[L]) / (a.B.u[L] - a.B.l[L])) * 100,
                          ),
                        )}%;
                        background:
                        linear-gradient(
                            90deg,
                            #5b6578,
                            #aab3c5
                        )
                    "
                ></b>

            </div>

        </div>
    `;

  const f = a.fin;

  const ttm = (x) => x.reduce((p, c) => p + c, 0);

  $("#fin").innerHTML = [
    ["Revenue", cr(ttm(f.rev))],
    ["Net Profit", cr(ttm(f.np))],
    ["EPS (TTM)", "₹" + f2(ttm(f.eps))],
    ["P/E Ratio", s.pe.toFixed(1) + "x"],
  ]
    .map(
      (x) =>
        `<div>
                <small>${x[0]}</small>
                <b>${x[1]}</b>
            </div>`,
    )
    .join("");

  const mx = Math.max(...[21, 63, 126, 251].map((n) => Math.abs(a.ret(n))));

  $("#ret").innerHTML =
    [
      ["1M", 21],
      ["3M", 63],
      ["6M", 126],
      ["1Y", 251],
    ]
      .map(([t, n]) => {
        const v = a.ret(n);

        return `
                <div class="rr">

                    <span class="mute">
                        ${t}
                    </span>

                    <div class="bar">

                        <b
                            style="
                                width:${(Math.abs(v) / mx) * 100}%;
                                background:${`var(--${cls(v, 1)})`};
                            "
                        ></b>

                    </div>

                    <b class="${cls(v, 1)}">
                        ${pc(v, 1)}
                    </b>

                </div>
            `;
      })
      .join("") +
    `<div class="note">
            Total return over each period · sample data
        </div>`;

  $("#rk").innerHTML =
    [
      ["Volatility (ann.)", a.vol.toFixed(1) + "%"],
      ["Max Drawdown (1Y)", `<span class="down">${a.dd.toFixed(1)}%</span>`],
      ["Beta (sample)", s.beta.toFixed(2)],
      ["1-day VaR 95%", `<span class="down">-${a.var95.toFixed(1)}%</span>`],
    ]
      .map(
        (x) =>
          `<div>
                <small>${x[0]}</small>
                <b>${x[1]}</b>
            </div>`,
      )
      .join("") +
    `<div
            style="
                grid-column:1/-1;
                display:flex;
                justify-content:space-between;
                align-items:center
            "
        >
            <small>Overall risk</small>

            <span
                class="badge2 ${["b-p", "b-m", "b-n"][a.risk]}"
            >
                ${rl.toUpperCase()}
            </span>
        </div>`;

  $("#nw").innerHTML = news()
    .slice(0, 4)
    .map(
      (n) =>
        `<div class="nw">

                <b>${n.h}</b>

                <span class="badge2 ${n.c}">
                    ${n.s}
                </span>

                <small>
                    ${n.src} · ${n.t}
                </small>

                <span></span>

            </div>`,
    )
    .join("");

  $("#sc").innerHTML = sectors()
    .map(([n, v]) => {
      const me = n == s.sec;

      return `
                <div class="sec ${me ? "me" : ""}">

                    <span>
                        ${n}${me ? " ★" : ""}
                    </span>

                    <div class="bar">

                        <b
                            style="
                                width:${Math.min(100, Math.abs(v) * 22)}%;
                                background:${`var(--${cls(v, 1)})`}
                            "
                        ></b>

                    </div>

                    <b class="${cls(v, 1)}">
                        ${pc(v, 1)}
                    </b>

                </div>
            `;
    })
    .join("");

  $("#ec").innerHTML = eco()
    .map(
      (e) =>
        `<div>

                <small>${e.l}</small>

                <b>${e.v}</b>

                <span
                    class="${e.c}"
                    style="font-size:11.5px"
                >
                    <i class="bi bi-${e.i}"></i>
                    ${e.d}
                </span>

            </div>`,
    )
    .join("");

  $("#fx").innerHTML = [
    ["Current Price", "₹" + f2(a.d[L]), ""],
    ["Forecast Price (30d)", "₹" + f2(a.fc.mid[29]), a.fdir],
    ["Expected Change", pc(a.exp), a.fdir],
    [
      "Forecast Trend",
      `<i class="bi bi-${
        a.exp > 1
          ? "arrow-up-right"
          : a.exp < -1
            ? "arrow-down-right"
            : "arrow-right"
      }"></i> ${a.trend}`,
      a.fdir,
    ],
  ]
    .map(
      (x) =>
        `<div>
                <small>${x[0]}</small>
                <b class="${x[2]}">
                    ${x[1]}
                </b>
            </div>`,
    )
    .join("");

  chartFc();

  first = false;
}

const news = () => {
  const s = A.s;

  return [
    {
      h: `${s.n} posts steady quarterly earnings with stable margins`,
      s: "Positive",
      c: "b-p",
      src: "Demo Wire",
      t: "06 Oct 2026, 09:30",
    },

    {
      h: `Analysts hold neutral view on ${s.sec} sector amid rate outlook`,
      s: "Neutral",
      c: "b-m",
      src: "Sample Markets",
      t: "05 Oct 2026, 16:10",
    },

    {
      h: `${s.n} faces input-cost pressure, management guides cautiously`,
      s: "Negative",
      c: "b-n",
      src: "Demo Business",
      t: "05 Oct 2026, 11:45",
    },

    {
      h: "Institutional flows into large caps rise as inflation cools",
      s: "Positive",
      c: "b-p",
      src: "Sample Economic Desk",
      t: "03 Oct 2026, 18:20",
    },

    {
      h: `${s.sec} peers report mixed order-book growth`,
      s: "Neutral",
      c: "b-m",
      src: "Demo Wire",
      t: "02 Oct 2026, 10:05",
    },
  ];
};

const sectors = () => {
  const r = rng(A.s.s);

  return SECS.map(([n, v]) => [n, v + (r() - 0.5) * 0.8]).sort(
    (x, y) => y[1] - x[1],
  );
};

const eco = () => [
  {
    l: "GDP Growth",
    v: "6.8%",
    d: "+0.2",
    c: "up",
    i: "arrow-up",
  },
  {
    l: "Inflation (CPI)",
    v: "4.6%",
    d: "-0.3",
    c: "down",
    i: "arrow-down",
  },
  {
    l: "Interest Rate",
    v: "6.25%",
    d: "0.00",
    c: "flat",
    i: "dash",
  },
  {
    l: "Unemployment",
    v: "7.1%",
    d: "+0.1",
    c: "up",
    i: "arrow-up",
  },
];

function counters() {
  $$("[data-c]").forEach((el) => {
    const t = +el.dataset.c,
      dc = +el.dataset.d,
      p = el.dataset.p || "",
      sf = el.dataset.s || "",
      sg = el.dataset.sg,
      t0 = performance.now();

    const set = (v) =>
      (el.textContent =
        p +
        (sg && v >= 0 ? "+" : "") +
        v.toLocaleString("en-IN", {
          minimumFractionDigits: dc,
          maximumFractionDigits: dc,
        }) +
        sf);

    if (matchMedia("(prefers-reduced-motion:reduce)").matches) return set(t);

    const step = (n) => {
      const k = Math.min(1, (n - t0) / 900);

      set(t * (1 - Math.pow(1 - k, 3)));

      if (k < 1) requestAnimationFrame(step);
    };

    requestAnimationFrame(step);
  });
}

/* =========================
   GENERIC CHART
========================= */

function draw(el, o) {
  const W = el.clientWidth || 600,
    H = o.h,
    pl = 48,
    pr = 8,
    pt = 8,
    pb = 20,
    all = [
      ...o.y,
      ...(o.bb ? o.bb.u.concat(o.bb.l).filter((x) => x != null) : []),
      ...(o.fc ? o.fc.hi.concat(o.fc.lo) : []),
    ],
    mn = Math.min(...all),
    mx = Math.max(...all),
    pd = (mx - mn) * 0.06,
    N = o.dates.length,
    X = (i) => pl + (i / (N - 1)) * (W - pl - pr),
    Y = (v) => pt + (1 - (v - mn + pd) / (mx - mn + 2 * pd)) * (H - pt - pb),
    P = (a, off = 0) =>
      a
        .map((v, i) =>
          v == null
            ? ""
            : (a.slice(0, i).some((x) => x != null) ? "L" : "M") +
              X(i + off).toFixed(1) +
              " " +
              Y(v).toFixed(1),
        )
        .join(""),
    id = "g" + el.id,
    an = o.anim ? "draw" : "",
    n = o.y.length - 1;

  let s = `
        <svg
            width="${W}"
            height="${H}"
        >

            <defs>

                <linearGradient
                    id="${id}"
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                >

                    <stop
                        offset="0"
                        stop-color="${o.col}"
                        stop-opacity=".3"
                    />

                    <stop
                        offset="1"
                        stop-color="${o.col}"
                        stop-opacity="0"
                    />

                </linearGradient>

            </defs>
    `;

  for (let i = 0; i < 5; i++) {
    const v = mn - pd + ((mx - mn + 2 * pd) * i) / 4;

    const y = Y(v);

    s += `
            <line
                x1="${pl}"
                x2="${W - pr}"
                y1="${y}"
                y2="${y}"
                stroke="rgba(255,255,255,.07)"
                stroke-dasharray="3 5"
            />

            <text
                x="${pl - 6}"
                y="${y + 3}"
                text-anchor="end"
                fill="#8e97aa"
                font-size="10"
            >
                ${f0(v)}
            </text>
        `;
  }

  for (let i = 0; i < 5; i++) {
    const j = Math.round((i * (N - 1)) / 4);

    s += `
            <text
                x="${Math.min(W - pr - 14, Math.max(pl + 10, X(j)))}"
                y="${H - 5}"
                text-anchor="middle"
                fill="#8e97aa"
                font-size="10"
            >
                ${fd(o.dates[j])}
            </text>
        `;
  }

  if (o.bb)
    s += `
            <path
                class="fade"
                d="${P(o.bb.u)}${[...o.bb.l]
                  .map((v, i) => [v, i])
                  .filter((x) => x[0] != null)
                  .reverse()
                  .map(
                    (x) => "L" + X(x[1]).toFixed(1) + " " + Y(x[0]).toFixed(1),
                  )
                  .join("")}Z"
                fill="rgba(142,151,170,.08)"
                stroke="rgba(142,151,170,.35)"
                stroke-width="1"
            />
        `;

  if (o.ema)
    s += `
            <path
                class="fade"
                d="${P(o.ema)}"
                fill="none"
                stroke="#ffffff"
                stroke-opacity=".55"
                stroke-width="1.2"
            />
        `;

  if (o.fc) {
    const c = [o.y[n], ...o.fc.mid];

    const u = [o.y[n], ...o.fc.hi];

    const l = [o.y[n], ...o.fc.lo];

    s += `

            <path
                class="fade"
                d="
                    ${u
                      .map(
                        (v, i) =>
                          (i ? "L" : "M") +
                          X(i + n).toFixed(1) +
                          " " +
                          Y(v).toFixed(1),
                      )
                      .join("")}

                    ${l
                      .map(
                        (v, i) =>
                          "L" + X(i + n).toFixed(1) + " " + Y(v).toFixed(1),
                      )
                      .reverse()
                      .join("")}

                    Z
                "
                fill="${o.fcol}"
                fill-opacity=".16"
            />

            <path
                class="fade"
                d="${P(c, n)}"
                fill="none"
                stroke="${o.fcol}"
                stroke-width="2"
                stroke-dasharray="6 5"
            />

        `;
  }

  s += `

        <path
            class="fade"
            d="
                ${P(o.y)}
                L${X(n)} ${H - pb}
                L${X(0)} ${H - pb}
                Z
            "
            fill="url(#${id})"
        />

        <path
            class="${an}"
            pathLength="1"
            d="${P(o.y)}"
            fill="none"
            stroke="${o.col}"
            stroke-width="2.2"
            stroke-linejoin="round"
        />

        <line
            class="cl"
            y1="${pt}"
            y2="${H - pb}"
            stroke="rgba(255,255,255,.28)"
            display="none"
        />

        <circle
            class="cd"
            r="4.5"
            fill="#fff"
            stroke="${o.col}"
            stroke-width="2"
            display="none"
        />

        </svg>

        <div class="tip"></div>
    `;

  el.innerHTML = s;

  const tip = $(".tip", el),
    cl = $(".cl", el),
    cd = $(".cd", el),
    all2 = o.y.concat(o.fc ? o.fc.mid : []);

  el.onmousemove = (e) => {
    const bx = el.getBoundingClientRect();

    const i = Math.max(
      0,
      Math.min(
        N - 1,
        Math.round(((e.clientX - bx.left - pl) / (W - pl - pr)) * (N - 1)),
      ),
    );

    const v = all2[i],
      x = X(i);

    cl.setAttribute("x1", x);
    cl.setAttribute("x2", x);
    cl.removeAttribute("display");

    cd.setAttribute("cx", x);
    cd.setAttribute("cy", Y(v));
    cd.setAttribute("stroke", i > n && o.fcol ? o.fcol : o.col);
    cd.removeAttribute("display");

    tip.style.display = "block";

    tip.innerHTML = `
            ${fdl(o.dates[i])}
            <br>
            <b>₹${f2(v)}</b>
            ${i > n ? ` <span style="color:${o.fcol}">forecast</span>` : ""}
        `;

    tip.style.left = Math.min(W - 120, x + 10) + "px";

    tip.style.top = "10px";
  };

  el.onmouseleave = () => {
    tip.style.display = "none";

    cl.setAttribute("display", "none");

    cd.setAttribute("display", "none");
  };
}

function futureDates(n) {
  const a = [],
    d = new Date(DATES[251]);

  while (a.length < n) {
    d.setDate(d.getDate() + 1);

    if (d.getDay() % 6) a.push(new Date(d));
  }

  return a;
}

function chartMain() {
  if (!A) return;

  const a = A,
    n = rg,
    sl = (x) => x.slice(-n),
    oe = $("#oe").checked,
    ob = $("#ob").checked,
    y = sl(a.d),
    chg = (y[y.length - 1] / y[0] - 1) * 100,
    dr = cls(chg);

  // Period change next to the title; the line colour follows the real movement
  $("#rc").innerHTML =
    `<span class="${dr}">${pc(chg)}</span> ` +
    `<span class="mute">${{ 21: "1M", 63: "3M", 126: "6M", 251: "1Y" }[n]}</span>`;

  draw($("#main"), {
    y,
    col: COL[dr],
    dates: sl(DATES),
    ema: oe ? sl(a.e20) : null,

    bb: ob
      ? {
          u: sl(a.B.u),
          l: sl(a.B.l),
        }
      : null,

    h: 310,
    anim: first || window._anim,
  });

  window._anim = false;
}

function chartFc() {
  const a = A;

  draw($("#fch"), {
    y: a.d.slice(-60),
    dates: [...DATES.slice(-60), ...futureDates(30)],
    fc: a.fc,
    col: "#aeb6c6",
    fcol: COL[a.fdir],
    h: 170,
    anim: true,
  });
}

/* =========================
   MODAL
========================= */

const tbl = (h, rows) =>
  `<table class="table">

        <thead>

            <tr>
                ${h.map((x) => `<th>${x}</th>`).join("")}
            </tr>

        </thead>

        <tbody>

            ${rows
              .map(
                (r) =>
                  `<tr>
                            ${r.map((c) => `<td>${c}</td>`).join("")}
                        </tr>`,
              )
              .join("")}

        </tbody>

    </table>`;

const DET = {
  tech: () => [
    "Technical Indicators · " + K,

    tbl(
      ["Indicator", "Value", "Reading"],

      [
        [
          "RSI (14)",
          A.R.toFixed(1),
          A.R > 70 ? "Overbought" : A.R < 30 ? "Oversold" : "Neutral",
        ],

        [
          "MACD line",
          A.mc[A.L].toFixed(2),
          A.hist > 0 ? "Above signal (bullish)" : "Below signal (bearish)",
        ],

        ["MACD signal", A.sg[A.L].toFixed(2), "9-period EMA of MACD"],

        ["EMA 20", f2(A.e20[A.L]), "Short-term trend"],

        [
          "EMA 50",
          f2(A.e50[A.L]),
          A.d[A.L] > A.e50[A.L] ? "Price above" : "Price below",
        ],

        ["Bollinger upper", f2(A.B.u[A.L]), "20-day, 2σ"],

        ["Bollinger lower", f2(A.B.l[A.L]), "20-day, 2σ"],
      ],
    ),
  ],

  fin: () => [
    "Company Financials · " + A.s.n,

    tbl(
      ["Quarter", "Revenue", "Net Profit", "EPS"],

      ["Q1 FY27", "Q4 FY26", "Q3 FY26", "Q2 FY26"].map((q, i) => [
        q,
        cr(A.fin.rev[i]),
        cr(A.fin.np[i]),
        "₹" + f2(A.fin.eps[i]),
      ]),
    ) +
      `<div class="note">
            P/E ${A.s.pe}x · net margin ≈
            ${(A.s.m * 100).toFixed(1)}%
            · fictional sample statements
        </div>`,
  ],

  ret: () => [
    "Historical Returns · " + K,

    tbl(
      ["Period", "Return"],

      [
        ["1 Week", 5],
        ["1 Month", 21],
        ["3 Months", 63],
        ["6 Months", 126],
        ["1 Year", 251],
      ].map(([t, n]) => [
        t,
        `<span class="${cls(A.ret(n))}">
                            ${pc(A.ret(n))}
                        </span>`,
      ]),
    ),
  ],

  risk: () => [
    "Risk Analysis · " + K,

    tbl(
      ["Metric", "Value"],

      [
        ["Annualised volatility", A.vol.toFixed(1) + "%"],

        ["Max drawdown (1Y)", `<span class="down">${A.dd.toFixed(1)}%</span>`],

        ["Beta (sample)", A.s.beta.toFixed(2)],

        [
          "1-day VaR (95%)",
          `<span class="down">-${A.var95.toFixed(1)}%</span>`,
        ],

        ["Risk level", ["Low", "Moderate", "High"][A.risk]],
      ],
    ),
  ],

  news: () => [
    "Financial News · sample headlines",

    news()
      .map(
        (n) =>
          `<div class="nw">

                    <b>${n.h}</b>

                    <span class="badge2 ${n.c}">
                        ${n.s}
                    </span>

                    <small>
                        ${n.src} · ${n.t}
                    </small>

                    <span></span>

                </div>`,
      )
      .join(""),
  ],

  sector: () => [
    "Sector Performance (1M)",

    tbl(
      ["Sector", "Change"],

      sectors().map(([n, v]) => [
        n,
        `<span class="${cls(v, 1)}">
                            ${pc(v, 1)}
                        </span>`,
      ]),
    ),
  ],

  eco: () => [
    "Economic Conditions · sample",

    tbl(
      ["Indicator", "Value", "Change"],

      eco().map((e) => [e.l, e.v, e.d]),
    ),
  ],

  fc: () => [
    "Price Forecast · " + K,

    tbl(
      ["Horizon", "Forecast", "Low", "High"],

      [5, 10, 20, 30].map((h) => [
        h + " days",
        `<span class="${cls(A.fc.mid[h - 1] / A.d[A.L] - 1)}">₹${f2(A.fc.mid[h - 1])}</span>`,
        "₹" + f2(A.fc.lo[h - 1]),
        "₹" + f2(A.fc.hi[h - 1]),
      ]),
    ) +
      `<div class="note">
            Simple drift-and-volatility projection
            on sample data. Not investment advice.
        </div>`,
  ],
};

const M = new bootstrap.Modal("#dm");

document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-d]");

  if (b && DET[b.dataset.d]) {
    const [t, h] = DET[b.dataset.d]();

    $("#dt").textContent = t;
    $("#db").innerHTML = h;

    M.show();
  }
});

/* =========================
   CONTROLS
========================= */

$("#sel").innerHTML = Object.entries(ST)
  .map(
    ([k, s]) =>
      `<option value="${k}">
                ${k}
            </option>`,
  )
  .join("");

$("#dl").innerHTML = Object.entries(ST)
  .map(
    ([k, s]) =>
      `<option value="${s.n}">
                ${k}
            </option>`,
  )
  .join("");

$("#form").onsubmit = (e) => {
  e.preventDefault();

  const v = $("#q").value.trim().toLowerCase();

  const k =
    Object.keys(ST).find(
      (k) => k.toLowerCase() == v || ST[k].n.toLowerCase() == v,
    ) ||
    Object.keys(ST).find(
      (k) => k.toLowerCase().includes(v) || ST[k].n.toLowerCase().includes(v),
    );

  if (!v || !k) {
    $("#err").textContent =
      "No match in the sample universe. Try: " + Object.keys(ST).join(", ");

    return;
  }

  $("#err").textContent = "";

  first = true;

  analyze(k);
};

$("#sel").onchange = (e) => {
  $("#err").textContent = "";

  first = true;

  analyze(e.target.value);
};

$("#rg").onclick = (e) => {
  const b = e.target.closest("button");

  if (!b) return;

  rg = +b.dataset.r;

  $$("#rg button").forEach((x) => x.classList.toggle("on", x == b));

  window._anim = true;

  chartMain();
};

$("#oe").onchange = $("#ob").onchange = chartMain;

let rz;

addEventListener("resize", () => {
  clearTimeout(rz);

  rz = setTimeout(() => {
    window._anim = false;

    chartMain();
    chartFc();
  }, 150);
});

/* =========================
   SCROLLSPY
========================= */

const links = $$("#sub a");

const io = new IntersectionObserver(
  (es) =>
    es.forEach((e) => {
      if (e.isIntersecting)
        links.forEach((l) =>
          l.classList.toggle("on", l.getAttribute("href") == "#" + e.target.id),
        );
    }),
  {
    rootMargin: "-120px 0px -60% 0px",
  },
);

links.forEach((l) => {
  const t = $(l.getAttribute("href"));

  t && io.observe(t);
});

/* =========================
   INITIAL STOCK
========================= */

analyze("RELIANCE");

/* =========================
   SHARED HEADER + FOOTER
   Same behaviour as index.html: navbar glass state on scroll,
   --nav-h for the sticky sub-navigation, footer reveal + particles.
   Wrapped in a function so it adds no globals.
========================= */

(function () {
  "use strict";

  /* ---- Navbar: glass background after scrolling + sticky offset ---- */
  var nav = document.querySelector(".fn-nav");
  if (nav) {
    var root = document.documentElement;

    var onScroll = function () {
      nav.classList.toggle("scrolled", window.scrollY > 20);
    };

    // Publish the navbar height as --nav-h so page-level sticky bars can sit
    // directly beneath it. Skipped while the mobile menu is open.
    var publishHeight = function () {
      if (
        nav.querySelector(".navbar-collapse.show, .navbar-collapse.collapsing")
      )
        return;
      root.style.setProperty("--nav-h", nav.offsetHeight + "px");
    };

    onScroll();
    publishHeight();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", publishHeight);
    nav.addEventListener("hidden.bs.collapse", publishHeight);
    // border-box: the navbar shrinks by changing its padding when scrolled
    if ("ResizeObserver" in window)
      new ResizeObserver(publishHeight).observe(nav, { box: "border-box" });
  }

  /* ---- Footer: reveal, floating particles, travelling point ---- */
  var ft = document.querySelector(".ft");
  if (ft) {
    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var svg = ft.querySelector(".ft-graph");
    var box = ft.querySelector(".ft-particles");

    if (!reduce && box) {
      for (var i = 0; i < 16; i++) {
        var p = document.createElement("i");
        p.style.left = Math.random() * 100 + "%";
        p.style.top = 30 + Math.random() * 60 + "%";
        p.style.setProperty("--t", 9 + Math.random() * 8 + "s");
        p.style.setProperty("--dl", Math.random() * 8 + "s");
        box.appendChild(p);
      }
    }

    // Hold the moving point until the footer is visible
    if (svg && svg.pauseAnimations) svg.pauseAnimations();

    new IntersectionObserver(
      function (entries, obs) {
        if (!entries[0].isIntersecting) return;
        ft.classList.add("in");
        if (svg && svg.unpauseAnimations && !reduce) svg.unpauseAnimations();
        obs.unobserve(ft);
      },
      { threshold: 0.25 },
    ).observe(ft);
  }
})();
