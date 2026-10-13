# AGENTS.md — JobBot

Instructions for AI agents and humans working on this repository.

Brand and voice (niche = tech, channel = terminal):
[docs/manifesto.md](docs/manifesto.md) — **búsqueda mientras programas**; HITL; never invent.

## Product / endgame

JobBot is a **local terminal-only** tool. Two loops, one source of truth
(`data/profile.yaml`; never invent experience):

```text
1) Standing presence (collaborative portals)
   LaTeX / PDF / profile.yaml
     → improve CV (advise)
     → every *active* portal in the shared company↔portal base
        has this candidate registered (when automatable) and up to date
     → jobbot status shows evidence of what is up

2) Apply to a vacancy
   profile.yaml → match / shortlist → package → application apply (HITL submit)
```

**Collaboration is the map, not the traveller.** Shared knowledge is who hires where
and what forms ask (companies / portals / form questions). Each person's CV, sessions,
passwords and applications stay on their machine.

**New candidate surface (target: two or three commands).** Someone arrives with a LaTeX
CV (often outside the repo: `paths.legacy_cv`, a private path — never commit real
`latex/cv.tex`). JobBot imports facts, helps present them, then syncs standing presence
against the collaborative portal base:

```bash
jobbot profile import-latex          # or import-pdf; promote-generated after review
jobbot cv advise --apply             # presentation only; confirms one by one
jobbot cv sync --apply               # permanentes + active companies (HITL; #43)
# Needs-account rows: signup sheet (#44). Fill when no account needed or session evidenced.
```

**Accounts, as far as automatable.** If an active portal in the base needs an account and
this workspace has none, JobBot may open the registration and **fill fields the profile
already answers** (and attach the built CV). It never invents a password, never accepts
terms alone, never solves CAPTCHA/2FA, and never clicks the final create/submit without
HITL confirmation. Irreversible steps stay human. Own accounts only.

**Local vault (opt-in, trusting users).** Some candidates keep portal passwords in
`data/.vault.yaml` (or `.local/.vault.yaml` after `jobbot init`) — hidden, `chmod 0600`,
gitignored, blocked by `pii_guard`. Hidden is **not** encryption: the OS user is the
trust boundary; disk encryption covers the disk; do not sync the file to Drive/Dropbox.
`jobbot secrets init` creates an empty vault; `secrets set` stores a value the human
types (`getpass` / `--password-stdin`, never argv). JobBot never invents an entry,
never prints one, never logs one (ops redaction strips vault values). `fill_login`
defaults false: CAPTCHA, 2FA, terms and submit stay human even when a password is
stored. Typing into a login form is a later opt-in ([#157](https://github.com/ljofreflor/jobbot/issues/157)).

**Oneshot ≠ presence.** `companies discover` only seeds *candidate* career URLs. It does
not create accounts or upload CVs. Presence is `cv sync` / propagate + assisted signup
against portals that were reviewed and `promote`d.

## Source of truth

```text
data/profile.yaml  →  Candidate (domain)
        │
   ┌────┼────┬─────────┬──────────────────────┐
   ▼    ▼    ▼         ▼                      ▼
 LaTeX Indeed LinkedIn  permanent portals   active company portals
                                              (collaborative base)
```

## Cargo lifecycle (primary loop)

```bash
jobbot jobs search "Senior Data Scientist" --location Santiago
# or LinkedIn recruiter posts → ATS:
jobbot linkedin sweep [QUERY] [--country CL] [--fixture PATH] [--cdp URL]
# or a hard job URL you already have (Get on Board / Indeed):
jobbot get https://www.getonbrd.com/empleos/.../slug
# jobbot get 'https://cl.indeed.com/viewjob?jk=...' [--fixture PATH]
# From a phone (no CAPTCHA): park the share link, drain later on desktop
jobbot capture 'https://…'   # always: leave as candidate (hard link / portal / unrecognized)
jobbot capture --list
jobbot get 'https://cl.indeed.com/viewjob?jk=...' --park
jobbot browser chrome-debug --site indeed
# Prefer email / magic link in that Chrome; if the mail hits your phone:
# jobbot indeed login --continue-url 'PEGAR_LINK_DEL_MAIL'
jobbot get --parked --cdp http://127.0.0.1:9222
jobbot jobs match J0001
jobbot jobs conditions J0001 # condiciones del aviso vs perfil (#166)
jobbot jobs shortlist
jobbot cv build --job J0001
jobbot cv advise # mejoras de presentación (determinista; --apply confirma una por una)
jobbot cv advise --job J0001 # scope a un aviso
jobbot cv tune-for J0001 # ~5% baseline desde un aviso (#54); --apply HITL
jobbot cv sync # presencia: permanentes + companies active (#43); --apply HITL por destino
jobbot status # CVs/perfiles + active company portals (evidencia local; alias: cv status)
jobbot application prepare J0001
jobbot application open J0001          # opens ATS/job URL; no auto-submit
jobbot application apply J0001         # dry-run prefill plan
jobbot application apply J0001 --apply # open ATS + prefill sheet (you submit)
jobbot application apply --all         # queue of eligible jobs (dry-run)
jobbot application apply --all --apply # open one by one; HITL between jobs / Next
jobbot profile suggest-from-market     # market language (no stdin; --ask for gaps)
jobbot profile suggest-from-market --job J0001
```

Job descriptions are pulled from **Indeed** (`jobs search`), **LinkedIn recruiter posts**
(`linkedin sweep`), or a **hard link** (`jobbot get URL` — live download is Get on Board
or Indeed; `--fixture` also ingests Indeed viewjob or career-page HTML). From a phone,
`jobbot capture URL` keeps the share as a **candidate** (hard-link inbox, company portal
candidate, or unrecognized list) with no fetch; `--park` queues the share URL under
`data/hard-link-inbox.txt` as the hard-link-only shortcut. On a desktop with Chrome CDP,
`jobbot get --parked` / `companies recon` finish the work (CAPTCHA stays HITL). Known ATS hosts
without a fetcher (or Indeed URL shapes we do not yet parse) are refused and recorded
as ops failures with class+message — tracking stripped from the stored command — so
`ops failure work` can open the issue→branch→PR lane. Manual `jobs add --file` is a fallback.
`profile.yaml` is never silently rewritten for an offer. Derived artifacts go under `output/jobs/Jxxxx/`.
Baseline may be updated only via **confirmed** market feedback (`profile suggest-from-market --promote`): rephrase/presentation and user-confirmed skills — never invented facts; never delete existing facts.

## Job URLs (always validate before handing one out)

- Before giving the user any posting URL, validate it: HTTP 200 after redirects, the page is the detail of **that** role (title and employer match), and it is not closed or expired as of today.
- Hand out the posting's canonical URL — never a search page, the portal home, or an ID-only URL when that form fails (e.g. trabajando.cl needs the slug).
- If the site blocks curl (Workday, LinkedIn, Computrabajo), check it in a browser in public view: no login, no CAPTCHA bypass.
- If it cannot be verified, mark it **"not verified"** and say why; never invent one or swap in another role.
- `jobbot jobs add --url` gets the already validated, canonical URL.

## MVP decisions (LinkedIn → ATS loop)

- **LinkedIn discovery:** recruiter **posts** with external ATS links (`linkedin sweep`); LinkedIn Jobs official is secondary.
- **Post links:** modern LinkedIn cards expose no `urn:li:activity`, so `linkedin sweep` reads each
 post's own URL from its "…" menu ("Copy link to post" → clipboard), resolves `lnkd.in` and strips
 tracking (`utm_*`, `rcm=<member id>`). `--no-copy-links` skips the extra click; without a link the
 author's profile is stored as fallback. Read-only: the menu is opened and closed, nothing shared.
- **Country preference:** `[search].countries` (default `CL`, falls back to `[indeed].country`) drops
 posts detected in other countries; `--country XX` overrides per run, `--any-country` lifts it.
 Remote only rescues a foreign post when it is not tied to a place ("100% remoto para LATAM" sí,
 "remota con visitas a Monterrey" no); `allow_remote = false` quita ese rescate. Países
 indetectables nunca se descartan.
- **Freshness:** `[search].max_age_days` (default 30) descarta posts viejos usando la fecha real que
 trae el activity id del link (`id >> 22` = ms epoch); `--max-age-days N` / `--any-age` por corrida.
 Sin fecha conocida no se descarta. `jobbot jobs backfill-dates` fecha lo ya guardado, offline.
- **ATS apply depth:** discover + store + detect portal + **prefill known fields**; user submits (`application apply --apply`). No auto-submit, no CAPTCHA bypass. A yes at a prompt is not a receipt: without portal evidence, status stays `prepared` (unknown whether it was submitted) and the URL is recorded on an `ApplicationEvent`. A posting whose text or page says the vacancy is filled is not stored as open and is not opened.
- **Email-only apply:** posts whose only apply route is an address become `ats_kind=email`
 (`mailto:`), with the post body as JD. `application apply --apply` builds the CV adapted to the
 job, opens Gmail compose and **uploads the PDF** (Playwright; `--cdp` to reuse your logged-in
 Chrome, `--no-attach` for compose URL only). JobBot never clicks Send.
- **LinkedIn-message apply:** posts whose only apply route is a DM / «mandame un mensaje» /
 `mensaje interno` keep the permalink as the apply surface (`ats_kind=linkedin`).
 `application apply --apply` opens the post (HITL). JobBot never sends InMail, never clicks
 Message/Send, and does not invent the unnamed client a headhunter is hiring for.
- **Market feedback:** `profile suggest-from-market` writes suggestions with no stdin by
  default (`--no-ask`). Gap prompts only with `--ask`; `--promote` still confirms before
  writing `profile.yaml`. Never invent; never delete baseline facts.
- **Domain-agnostic by rule:** the candidate may be a nurse, a journalist or an engineer, so **no
 module may gate behaviour on one field's vocabulary**, and none may hold a real employer, city or
 person. Enforced by `tests/unit/test_domain_agnostic.py`, one test per module.
 - JD skills come from the posting's own structure: list items, lead-ins (`Manejo de …`,
 `Experiencia en …`) and typography that marks a tool (`SEO`, `WordPress`, `C++`).
 - Requirement evidence comes from the profile's own wording, tolerating gender and plural
 (`geofísico`/`geofísica`). Role fit compares the job title against the titles actually held —
 there is no table of role families.
 - Market feedback reads its terms from the stored JDs; a confirmed skill lands in a neutral
 group; an imported CV keeps the skill groups its own sections used.
 - A post is discovered for saying it is hiring or how to apply, not for its field. Board
 searches (`getonboard search`, `torre search`, `linkedin sweep` with no query) run the
 profile's `search_queries`; without them, the set `profile queries` derives from experience
 (skills a role backs, phrases repeated across achievements, titles held — most recent
 first). The headline is a last fallback only; no default role lives in the code.
 `search_queries` is a preference the candidate edits, not a professional fact.
 - The matcher also reads the posting against the profile: a declared skill, specialty or
 degree the posting names, or an achievement it echoes, is strong evidence. That side can
 only add, never lower a score. Page chrome (dates, clock times, salaries, currency codes,
 `Label: value`, shouted headings, ATS field labels) is never a requirement. When every
 scored job lands at 0%, commands print a matcher alert instead of a silent empty list.
 - Equivalence tables (`jobs/normalization.py`) are allowed **because an unknown term falls
 through unchanged**: they add recall for names of the same thing, never a gate.
- **PDF CV import:** `profile import-pdf` reads the text layer only (no OCR, no models). A PDF has
 no structure, so the parser locates each role by its date (a range, a range whose months share
 one year — `julio – agosto 2026` — or a single right-aligned year) and then picks company and
 title by scoring the nearby lines, never by a fixed position. The employer may run long and end
 in a full stop, so the evidence that a line names one is the place it closes with, not its
 length. A company is never inherited unless a previous role actually named one.
 What it cannot resolve becomes a warning (glued text with no space glyphs, roles stranded
 outside the experience section when a two-column export interleaves columns); the generated YAML
 is always reviewed before `promote-generated`.
 Fixture PDFs are built at test time (`tests/fixtures/cv_pdf.py`): no binary CV is ever committed.
- **Broken font maps:** Word embeds one subset font per style and sometimes leaves a ligature out
 of `/ToUnicode`, so pypdf falls back to the raw byte and `instituciones` reads `insVtuciones`
 while the same font still writes a genuine `V`. `profile/pdf_glyphs.py` repairs the map before
 extraction, because after it the two characters are identical. The evidence is the advance width
 in `/Widths`: a glyph as wide as `t` plus `i`, and as wide as no other pair, is the `ti`
 ligature; a subset too small to prove it follows a sibling subset of the same base font at the
 same width. A width that fits two ligatures (`fi` and `fl` are the same) is reported, never
 guessed.
- **Torre:** `torre search` usa la búsqueda pública de oportunidades (JSON, sin navegador). El
 payload trae los requisitos con su experiencia exigida, así que las skills no salen de parsear
 prosa; el JD completo vive en una página client-rendered, por lo que una oferta de Torre es una
 pista para abrir, no un JD completo. El payload también lista a las personas detrás del aviso:
 nada bajo `members` llega nunca a un `JobPosting`. Cuando la oportunidad apunta a un ATS externo,
 esa URL es la que se guarda y alimenta el registro de empresas. Estado cerrado, fecha límite,
 idiomas con su fluidez, países de residencia y si la compensación es visible quedan escritos en
 el texto guardado para que `jobs conditions` los lea offline.
- **Condiciones del aviso ([#166](https://github.com/ljofreflor/jobbot/issues/166)):** antes de
 postular, `jobs conditions Jxxxx` lee del aviso guardado (offline, determinista, sin LLM) lo que
 condiciona la postulación: cerrado o fecha límite vencida, residencia o permiso de trabajo,
 idioma con nivel CEFR, requisitos excluyentes vs deseables, contrato (prestador de servicios vs
 indefinido), renta visible u oculta, modalidad, disponibilidad e instrucciones. Las pistas son
 estructurales (frases como "must reside in", niveles A1–C2, "excluyente"/"required"), nunca el
 vocabulario de una profesión. Cada condición recibe ✅ cumple (cita la evidencia), ⚠️ pregunta
 exacta al candidato o ❌ impedimento (exit 1, sin registrar falla de ops). Los hechos salen de
 `profile.yaml`; lo que el perfil no tiene (nivel de idioma, países donde puede trabajar, si acepta
 contrato de prestador, reubicación, preaviso, expectativa de renta) sale de
 `data/application_answers.yaml` — local, gitignored y bloqueado por `pii_guard`; plantilla en
 `data/application_answers.example.yaml` — y el `answers.yaml` del paquete del aviso lo pisa
 para ese aviso. Es preferencia del candidato, no un hecho profesional. Respuesta en blanco =
 pregunta, nunca suposición. Un excluyente que el perfil no respalda es ⚠️, no ❌: solo el
 candidato sabe si lo cumple, y nunca se agrega al perfil sin que lo confirme.
- **Company career platforms:** `jobbot companies` mantiene conocimiento **público** empresa↔portales
 (0..N career sites por empresa: portal propio, Workday, Greenhouse de filial…). Provenance por
 observación, dedup por URL canónica (sin query/fragment), contradicción → `stale` sin sobreescribir,
 y ATS `unknown` salvo evidencia técnica (host, redirect, marcador HTML embebido). `linkedin sweep`
 `jobs search` y `jobs add` alimentan candidatos (los job boards se omiten); solo `companies
 promote` los vuelve activos. Los nombres reservados para documentación y pruebas
 (`example.com/.net/.org`, `*.example`, `*.test`, `*.invalid`, `localhost`) nunca se guardan:
 el registro los rechaza con un mensaje claro. `companies discover`
 es un **oneshot** que escribe candidatos en `output/discovery/` y nunca toca `data/companies.yaml`;
 HTTP 200 no es evidencia y un sitio que nos rechaza (403/conexión cortada) se reporta como
 desconocido, no como ausencia. Compartir siempre vía `companies export` (solo activos, sin PII).
- **Reglas de portales decididas ([#269](https://github.com/ljofreflor/jobbot/issues/269); el
  código todavía no las aplica todas):**
  - **Promoción:** un sitio pasa solo a `active` cuando su ATS tiene evidencia técnica (regla de
    host, redirección o marcador HTML embebido), y la salida del comando lo informa. Con ATS
    `unknown`, la promoción sigue siendo manual (`companies promote`). El uso local por sí solo no
    promueve ([#52](https://github.com/ljofreflor/jobbot/issues/52)). Un sitio `rejected`, uno
    `stale` por contradicción, una bolsa de empleo o el tenant de un agregador nunca se promueven
    solos.
  - **Compartir ([#106](https://github.com/ljofreflor/jobbot/issues/106)):** sin opt-in no sale
    nada de la máquina. La persona da el opt-in una vez por workspace, puede revocarlo y tiene una
    cola de salida que puede revisar y vaciar; con opt-in activo los aportes fluyen sin
    confirmación por aporte.
  - **Un solo modelo:** el catálogo de fuentes ([#265](https://github.com/ljofreflor/jobbot/issues/265))
    se fusiona en el registro de `companies`; no se crea un registro paralelo de empleador↔canal.
  - **Registros viejos:** cuando mejora un detector, los sitios ya guardados se revisan con
    `companies recheck` ([#270](https://github.com/ljofreflor/jobbot/issues/270)): la nueva
    evidencia entra como observación y nunca pisa la anterior.
- **Recon por dentro ([#45](https://github.com/ljofreflor/jobbot/issues/45)):** el oneshot mira
  **desde fuera**; la verdad de componentes (ATS, campos de registro, dónde se sube el CV) se
  aprende **entrando**. `companies recon NOMBRE` captura el HTML de la página (fixture o CDP
  tras login HITL), corre `detect_ats_in_html` + `form-learn`, y con `--apply` guarda observación
  técnica + preguntas del formulario. No crea la cuenta, no inventa ATS desde el hostname, y
  alimenta [#43](https://github.com/ljofreflor/jobbot/issues/43) / [#44](https://github.com/ljofreflor/jobbot/issues/44).
- **Qué pide un formulario:** `portals form-learn URL --fetch|--fixture PATH` lee un formulario de
  postulación y guarda **solo las preguntas**: etiqueta, tipo, obligatoriedad, opciones de un select
  y qué archivos acepta. También nombra botones **Sign in with Google/LinkedIn/…** si están en la
  página (HITL; nunca inicia OAuth). Nunca guarda un valor tipeado, un token oculto ni el teléfono de
  ejemplo de un placeholder, y no envía nada. `application apply --apply` lo aprende de paso, sin
  bloquear la postulación si la página no se puede leer (queda como `unknown`, no como formulario
  vacío). `data/form_knowledge.yaml` es local (gitignored + `pii_guard`) y no se comparte: es el
  insumo que `cv advise` usa para saber qué preguntan realmente las empresas.
- **Registro de cuenta (asistido, HITL):** el endgame es que un portal *active* de la base
  colaborativa pueda quedar con cuenta + perfil/CV al día para este candidato. Hoy
  `companies signup NOMBRE` abre el portal y lista qué pide vs `profile.yaml`.
  Con `--apply` rellena campos que el perfil ya responde y puede adjuntar el PDF;
  **prohibido** inventar contraseña, aceptar términos solo, resolver
  CAPTCHA/2FA o pulsar crear/enviar sin confirmación. Si la página ofrece **Sign in with
  Google / LinkedIn / Microsoft / Apple**, `form-learn` y la hoja de signup lo **nombran**
  (`jobbot.portals.sso`); vos clicás el proveedor — JobBot nunca inicia OAuth. Un campo
  URL de perfil LinkedIn o un enlace de footer no cuentan como SSO. El módulo de sheet
  (`jobbot.companies.signup`) sigue sin cliente HTTP propio (la hoja es pura); el driver
  de relleno vive en `adapters/ats/signup_fill.py`, detrás de `--apply` + confirm. ATS sin cuenta
  (Greenhouse, Lever, Ashby) lo declaran; sin evidencia → `unknown`.
- **Asesor de presentación:** `cv advise` propone **pocas** mejoras por corrida en tres ejes
  (legibilidad de máquina, lenguaje, puesta en página) usando JD guardados, formularios observados y
  prácticas de reclutamiento que promoviste. El eje de lenguaje empuja **densidad y claridad**
  (mismo hecho, menos palabras); el gate rechaza floritura (texto más largo sin término de mercado
  respaldado, o solo intensificadores). Dos invariantes se **verifican**, no se prometen: una
  sugerencia no puede afirmar nada que el perfil no respalde (reusa el detector de invención de
  `nlp/refine.py`) ni perder una cifra o un nombre propio del texto actual; lo que falla se descarta
  antes de mostrarse. `--job Jxxxx` limita el alcance a un aviso; `cv tune-for` (#54) ingiere un
  hard link si hace falta y corre el mismo advise acotado (presupuesto 3, tope 5). `--apply`
  confirma una por una (default N, `skip-all` corta) y respalda `profile.yaml` con
  `profile.yaml.bak.<stamp>`; la bitácora (`output/cv/advice_log.yaml`) evita repetir lo que ya
  rechazaste.
- **Economía de tokens:** el nivel determinista es el default y no contacta a nadie. `--llm` manda
  **una línea**, nunca el CV completo, con el contacto redactado del prompt; `--llm-deep` solo entra
  si el nivel barato no produjo algo válido. Caché por hash de contenido más modelo, presupuesto por
  corrida (`--max-llm-calls`) y `--dry-run` que imprime qué se enviaría y cuánto sin gastar. Toda
  salida del LLM pasa la misma validación determinista: si inventa o borra, se descarta y queda la
  sugerencia determinista. La suite corre sin red, sin API key y sin el extra `llm`.
- **Mejora diaria del CV (ritual):** el CV debe seguir mejorando con lo que enseñan los JD
  guardados, así que el agente **propone una mejora por día** sin que se la pidan y el candidato
  **confirma**. Con datos locales (`data/profile.yaml` + jobs guardados), toca si el marcador
  `output/cv/improvement_proposal.yaml` (gitignored) no existe o su `last_proposed` es anterior a
  hoy (fecha local). Si toca: `jobbot cv advise` (dry-run) + `jobbot profile suggest-from-market`
  (sin stdin) y proponer **una sola**: la de mayor impacto que no esté en `proposed:` del marcador
  ni rechazada en `output/cv/advice_log.yaml` (preferir presentación respaldada por muchos JD; una
  brecha va solo como pregunta para que el candidato confirme el hecho). Algo ya propuesto vuelve
  solo si su evidencia en los JD creció de forma material. Sin nada nuevo, decirlo en una línea.
  Siempre actualizar el marcador: `last_proposed: AAAA-MM-DD`, `jobs_seen: N` (IDs únicos en
  `jobbot jobs shortlist`) y `proposed:` con `key` (`advise:<id>`, `gap:<término>`,
  `market:<slug>`), `date` y `jds`. Nada se aplica sin un sí explícito (`cv advise --apply` y
  `suggest-from-market --promote` confirman); nunca inventar. Un clon sin datos locales lo omite.
- **Conocimiento de reclutamiento:** `recruiters discover|list|show|promote|reject|export` guarda
  **prácticas públicas**, no personas: el modelo no tiene campo para autor, empleador ni contacto.
  Respeta `robots.txt`, deja fuera lo que está detrás de login (no fue publicado para nosotros) y
  reporta un rechazo como rechazo. Candidato hasta que hagas `promote`; solo lo activo llega a
  `cv advise`. `data/recruiters.yaml` es local; se comparte vía `recruiters export`.
- **Get on Board:** mantenedor de **perfil permanente** con **computación acumulativa**:
  `getonboard prepare` refina el draft previo (no lo tira) usando `profile.yaml` como hechos;
  `--seed` importa texto viejo del portal; `--llm` usa LangChain si `jobbot[llm]` + `OPENAI_API_KEY`;
  `--cold` solo si quieres partir de cero. Historia en `output/getonboard/history/`.
  HITL: https://www.getonbrd.com/webpros/edit + Tus CVs. `application prepare` reusa los textos.

## Workspaces (several candidates, one checkout)

A checkout may hold test CVs next to the real profile. The current directory is not
enough to keep them apart: every workspace numbers its jobs from `J0001`, so one command
run from the wrong folder overwrites another person's `output/jobs/J0001/` under the same
file names, silently.

- **Selection is explicit:** `jobbot --workspace NAME …` (or `JOBBOT_WORKSPACE`) resolves
  `data/`, `output/` and the database under `sandboxes/NAME/`, whatever the current
  directory is. Templates come from the checkout, because they are code, not data.
  Without a workspace nothing changes: the current directory is the root, as before.
- **Owner stamp:** the first run stamps `data/` and `output/` with a fingerprint of the
  profile's name (`.jobbot-owner.json`, a hash — never the name). A profile that does not
  match the stamp stops the command with exit `2` before writing anything; taking a
  directory over is deliberate (`jobbot workspace adopt`). This also protects the real
  `data/` from a test CV dropped over `data/profile.yaml`.
- **A selected workspace ignores `~/.config/jobbot/config.toml`**, whose absolute paths
  would otherwise reach into the real profile from inside a sandbox.
- **`sandboxes/` is somebody else's PII:** gitignored and blocked by the PII guard.
  Delete a test CV's workspace when you are done with it (`jobbot workspace delete NAME`).
- **Advisor:** `jobbot advisor status` lists every sandbox by owner fingerprint (never the
  name), job count, prepared applications, whether today's CV proposal exists, and a
  retention warning. `jobbot --workspace NAME advisor report` writes that client's
  summary only, redacted. Consent lives in `data/consent.yaml` inside the sandbox.
- **Browser account:** a signed-in tab is `ready` for Gmail or LinkedIn only when the
  page text matches this workspace. Another account is `wrong_account` and blocks
  `browser login --apply` and `application apply --apply`. The other identity is not printed.
  A datacenter browser per client is out of scope; proxies and stealth stay forbidden.

## Portal adapters

Matching and packages stay portal-agnostic. New sites implement:

- `JobSourceAdapter` — discovery via `get_job_source()` in [`src/jobbot/jobs/sources.py`](src/jobbot/jobs/sources.py) (Indeed, LinkedIn posts, GetOnBoard)
- `ApplicationPortalAdapter` — prefill/attach from Candidate + package ([`src/jobbot/adapters/base.py`](src/jobbot/adapters/base.py); registry in [`src/jobbot/adapters/ats/registry.py`](src/jobbot/adapters/ats/registry.py))
- Portal registry — `data/portals.yaml` via `jobbot portals list|add|detect`; auto-learned from sweep URLs

Inject only known fields; HITL for salary/visa/English/CAPTCHA. Prioridad actual de verticales:
Workday de punta a punta ([#214](https://github.com/ljofreflor/jobbot/issues/214)), en el orden
de esa épica ([#269](https://github.com/ljofreflor/jobbot/issues/269)).

## Domain direction

`DOMAIN (Candidate) → adapters` — never the reverse. One model: `Candidate`.

## Safety / platform

- Own accounts only. No CAPTCHA solving, 2FA bypass, stealth, proxies, telemetry.
- Public trust signal is the OpenSSF Scorecard badge (Linux Foundation, OSV vulnerabilities),
  published by `.github/workflows/scorecard.yml` on `main`. Do not replace it with a self-scored badge.
- Failures: local `ops_failures` in SQLite + `output/ops/failures/`; GitHub issues only via HITL
  `jobbot ops failure issue` (never auto on crash). Every issue opened that way (and any
  `gh issue create`) must be assigned to Cursor — login `cursoragent` — so it is never left
  unassigned; see Planning. Maintainer lane is bash:
  `jobbot ops failure work Fxxxx` prints (or with `--apply` opens) issue → `git fetch` →
  branch → PR → triage → re-run ([#46](https://github.com/ljofreflor/jobbot/issues/46)); never
  auto-commit / push / merge.
- **PII:** never commit `data/profile.yaml`, `data/portals.yaml`, `data/companies.yaml`, SQLite, `browser-data/`, `sandboxes/`, or `output/`. Track only `*.example.yaml` templates.
- **PII guard:** `make hooks` enables `.githooks/pre-commit` (`jobbot.ops.pii_guard`) — blocked paths + real-looking email/phone/RUT/home-path detection. Fixtures and examples allowlisted. `pii_guard.redact()` is the one place that defines what counts as contact data, reused wherever text leaves your files (learned form labels, LLM prompts). The hook only runs where it was installed, so the suite also scans every tracked file (`pii_guard.scan_tracked()`, `python -m jobbot.ops.pii_guard --all`): a commit that skipped the hook still fails CI.
- **Which commits run the suite:** `jobbot.ops.precommit.tests_needed()` decides, and it is unit-tested instead of living as a shell regex. Policy counts as behaviour: editing **this file** runs the tests, because for an agent working from a clone this file is the whole policy.
- **Polite web reading:** the one-shot and `recruiters discover` obey `robots.txt` via `RobotsPolicy`, cached per host. Being told not to read a page is reported as *omitted*; being unable to read it (403, 429, 5xx, dropped connection) is reported as *refused*. Neither ever becomes "there is nothing there".
- **Private LaTeX CV:** tracked dummy is `latex/cv.tex.demo` only; real `.tex`/`latex/cv.tex` stay gitignored. Prefer `paths.legacy_cv` outside the repo or a local ignored copy. See `latex/README.md`.
- LinkedIn: read-only audit by default. **Exception:** `linkedin sync --section publications`
  writes Publications only (dry-run default; `--apply` + per-item confirmation unless `--yes`).
- Indeed writes: dry-run default; `--apply` + confirmation.
- **Session preflight:** `jobbot.browser.sessions` reports per-site state from evidence only
  (`ready` needs an open signed-in page; a live port proves nothing). JobBot never auto-attaches:
  it suggests `--cdp`. A persistent profile held by another Chrome is `profile_busy` and blocks
  that destination up front (`BrowserSession` also refuses to launch over it).
 A debugging port held by a Chrome whose profile lives outside this workspace's browser data
 is reported busy without reading its tabs, and a suggested `--port` is never one a Chrome holds.
  `jobbot browser login` is the first pass over permanent sites plus company portals that are
  `active` or `candidate` and may need an account ([#56](https://github.com/ljofreflor/jobbot/issues/56)):
  dry-run by default; `--apply` opens the next gap and stops. The password, CAPTCHA and 2FA stay
  human unless the local vault has `fill_login` (not shipped yet; [#157](https://github.com/ljofreflor/jobbot/issues/157)).
  A company tab is `unknown`, never `ready`. Visiting a candidate does not promote it.
- **Focus:** JobBot abre páginas en segundo plano; no roba el foco. Todo pasa por
  `jobbot.browser.background` (`open -g` en macOS, `webbrowser` con `autoraise=False` fuera,
  pestañas CDP con `Target.createTarget` `background: true`) e imprime dónde quedó la página.
  `JOBBOT_BROWSER_FOCUS=1` vuelve al primer plano. Los tests nunca abren un navegador real.
- Removals ignored by default.

## Regression tests (mandatory)

Every bug/failure → unit test that fails first, then fix. Prefer fixtures over live portals.

## Dependencies

Before hand-rolling something generic (HTML, URLs, dates, emails, secrets, LaTeX), read
[docs/library-audit.md](docs/library-audit.md): it records what we replaced with a maintained
library, what we keep ours and why, and which migrations are open issues. Add a row when you
decide either way. Dependencies must be light, pure-python and offline — no downloadable models,
no service that phones home.

## Design economics (slow once, fast after)

A model can answer many questions here without writing a file: read a posting, judge a match,
extract an address. That answer is expensive, unverifiable and gone at the end of the chat.
The same work as a function is cheap forever and can be tested. So work that repeats gets
**promoted** into code, and after that it gets **called**, not re-derived.

The practice is not ours: it is the rule of three (extract at the third duplication) plus
knowledge compilation (costly deliberate reasoning becomes an automatic procedure), and in
agent terms the split between making a tool once and using it many times.

**When to promote.** At the third time the same analysis is asked, or the first time if the
repetition is predictable: a step of the cargo loop, or anything another agent would have to
re-derive from the same inputs. Do not promote on a hunch — a speculative helper is dead code
with a test attached, the same waste wearing a convincing costume.

**What a promotion must ship.**

- The function in the module that owns the subject, not in `cli.py`.
- A CLI entry only if a human will run it.
- A test that fails first (see above). Untested code is not a promotion, it is a draft.
- Its line in [docs/capabilities.md](docs/capabilities.md), so the next agent finds it
  (`make capabilities` regenerates it; a stale index fails the suite).

**What to call instead of re-deriving.**

- Leer [docs/capabilities.md](docs/capabilities.md) antes de buscar en el árbol: con más de cien
  módulos, un `grep` a ciegas cuesta más que el índice. Las cifras viven en el índice, que se
  regenera solo; no se copian aquí.
- Read [docs/library-audit.md](docs/library-audit.md) before hand-rolling something generic.
- Run `uv run jobbot …` instead of reasoning out an answer the CLI already prints, and read
  the command's output instead of pasting whole files into context.

This is not only about tokens. The deterministic path is the auditable one: never inventing
experience, and stopping for HITL, are guarantees that live in code and its tests — not in the
memory of a conversation.

## Planning (before a plan or feature branch)

Product work is tracked in GitHub issues. Agents re-deriving the same endgame in chat while
an issue already holds acceptance tests wastes everyone's time.

1. Before drafting a plan or opening a feature branch for product work, run
   `gh issue list --state open` (and search by keyword if needed).
2. Prefer **extending or closing an existing issue** over a parallel design that re-describes
   the same endgame (e.g. standing presence → [#43](https://github.com/ljofreflor/jobbot/issues/43)
   / assisted signup → [#44](https://github.com/ljofreflor/jobbot/issues/44)
   / portal recon inside → [#45](https://github.com/ljofreflor/jobbot/issues/45)).
3. If the work is genuinely new, open or update an issue first (HITL), then plan against that
   number. Antes de `gh issue create`, buscar el título (`gh issue list --state all --search
   "in:title …"`); una creación que falló no se reintenta sin volver a buscar.
4. Cite issue numbers in the plan and in PR bodies.
5. **Assign every GitHub issue to Cursor.** On `gh issue create` and on
   `jobbot ops failure issue`, pass `--assignee cursoragent` (or
   `gh issue edit N --add-assignee cursoragent` right after create). Agents must not leave
   issues unassigned. Login is `cursoragent` (GitHub User “Cursor Agent”); the App bot
   `cursor[bot]` **cannot** be an issue assignee. `cursoragent` needs **write** on the repo
   to appear in assignable users (read via the Cursor GitHub App is not enough). Until that
   write collaborator is in place, apply the `cursor` label as the ownership signal and keep
   a write invite open — then retry `--add-assignee cursoragent`. Prefer the real assignee
   over the label alone.

## Local branches (periodic cleanup)

A deleted remote branch leaves the local one behind. Once per local day, ask (HITL)
before removing locals whose upstream is already gone. Do not ask again the same day.

The marker is `output/ops/branch_cleanup.yaml` (under `output/`, gitignored):
`last_asked: YYYY-MM-DD`. A clone with no `output/` skips the sweep. Update
`last_asked` after the question, whether the answer is yes or no.

When it is due:

1. `git fetch --prune`.
2. List local branches other than `main` and `develop` whose upstream is `gone`.
   A branch that was never pushed is not in this list.
3. Ask once, naming each branch. The delete set is whatever is already contained in
   `develop` (`git merge-base --is-ancestor`). A tip that is not in `develop` stays;
   do not merge it into `develop` and do not force-delete it unless the human names
   that branch and asks for it.
4. On yes: if the current branch is one of them, `git switch develop` first. If that
   branch has uncommitted work, say so and stop — do not switch, do not stash. Then
   `git branch -d` each merged branch. Never delete `main` or `develop`.

When this same turn deletes a remote branch (`git push origin --delete`, a PR merge
that deletes the head, `gh pr close` after the remote is gone), delete the matching
local in that turn: switch to `develop` first if you are on it, `-d` only, and stop
to ask before a force-delete if the local tip is not in `develop`. The daily question
covers whatever that turn missed.

## Remote agents (issues, cloud, CI)

An agent working from a clone only has what git tracks, and the PII lives outside git:
`data/profile.yaml`, `data/portals.yaml`, `data/companies.yaml`, the SQLite database,
`browser-data/`, `output/` and the real `latex/cv.tex` are **not** there.

So, when working on an issue without the local machine:

- Build the failing test from a fixture under `tests/fixtures/`; never assume stored jobs (`J0047`)
  or a real profile exist.
- If closing the issue needs real data (legacy CV import, a stored post, a logged-in browser),
  ship the code plus fixture tests and say in the PR which check the human has to run locally.
- Never add a fixture with real PII. `*.example.yaml` and `latex/cv.tex.demo` are the templates.
- `.cursor/` is local, so this file is the whole policy: read it before touching anything.
- Product and ops issues are Cursor-owned: assignee `cursoragent` (fallback label `cursor`).
  Do not open or leave an issue without that ownership signal.

## Verify

```bash
uv sync --group dev
uv run ruff check .
uv run mypy src
uv run pytest
make coverage   # unit suite + ≥80% line gate (see [tool.coverage] in pyproject.toml)
```

CI (`.github/workflows/ci.yml`) runs the same checks on `develop` / `main` and on PRs.

Branch gates:

- **feature → `develop`:** 100% of unit tests must pass, coverage ≥80%.
- **`develop` → `main`:** at least **95%** of unit tests must pass, coverage ≥80%.

Every feature, fix or docs PR targets **`develop`** (`gh pr create --base develop`), whoever
opens it, cloud agents included. `main` only receives the `develop` → `main` release PR.
A PR merged straight into `main` forks the history: `develop` then has to merge `main`
back, and every conflict that merge resolves is a chance to drop a fix.

A change is not delivered until its behaviour has a unit test. `cli.py` and live
Playwright portal clients are omitted from the line count (they still have focused
unit tests) so the gate measures offline, fixture-backed code.

### CI failures (detect → fix)

When CI is red on a PR or push you are working on, **resolve it** — do not stop at reporting the check name.

1. **Read the failed logs** (`gh pr checks`, `gh run view <id> --log-failed`) until you know the first failing step and the concrete error (ruff/mypy/pytest/coverage).
2. **Fix the root cause** locally with the same Verify commands; push the fix on the same feature branch (or open a follow-up PR into `develop` if the breakage is already merged). Add a regression unit test when the failure is behavioural.
3. **HITL only where it matters:** ask before merging to `develop`/`main`, force-push, amending shared history, or anything that touches PII / live portals. The human does not need to approve reading logs or applying a mechanical lint/test fix.

Default posture: red CI → logs → fix → green CI. Summarize what broke and what you changed after the fix is in.

## Key commands

```bash
uv run jobbot profile validate
uv run jobbot profile import-latex
uv run jobbot profile import-pdf /path/to/cv.pdf # PDF con capa de texto; sin OCR
uv run jobbot cv build
uv run jobbot cv build --job J0001            # moderncv (tu diseño) por defecto
uv run jobbot cv build --job J0001 --style plain
uv run jobbot cv sync                      # plan: permanentes + companies active (#43)
uv run jobbot cv sync --apply              # HITL: permanentes + fill/signup sheet por destino
uv run jobbot cv propagate                 # alias permanente-only de sync (sin filas companies)
uv run jobbot cv propagate --targets permanent --apply
uv run jobbot status                       # permanentes + active company portals (evidencia)
# Signup fill beyond the sheet: issue #44
uv run jobbot companies signup NOMBRE --apply [--cdp URL]  # fill known fields; HITL create
uv run jobbot cv advise                    # determinista, sin tokens
uv run jobbot cv advise --job J0001        # scope a un aviso
uv run jobbot cv advise --apply            # confirma una por una → profile.yaml (con backup)
uv run jobbot cv tune-for J0001            # ~5% baseline desde un aviso (#54)
uv run jobbot cv tune-for 'https://…' --apply
uv run jobbot cv advise --llm --dry-run    # qué se enviaría y cuánto, sin gastar
uv run jobbot cv advise --llm --max-llm-calls 3
uv run jobbot jobs add --file tests/fixtures/jobs/senior_ds_retail.txt
uv run jobbot get https://www.getonbrd.com/empleos/.../slug   # hard link → CV + package
uv run jobbot get URL --apply --cdp http://127.0.0.1:9224     # + open ATS (HITL)
uv run jobbot jobs match J0001
uv run jobbot jobs conditions J0001 # ✅/⚠️/❌; exit 1 si hay impedimento
uv run jobbot jobs conditions --all-prepared --json
uv run jobbot application prepare J0001
uv run jobbot indeed login|pull|diff|sync --section headline
uv run jobbot linkedin login|pull|diff
uv run jobbot linkedin sync --section publications          # dry-run
uv run jobbot linkedin sync --section publications --apply  # confirm each
uv run jobbot linkedin sweep                    # queries del perfil (profile queries)
uv run jobbot linkedin sweep --max-queries 5
uv run jobbot linkedin sweep "enviar CV" --country CL --country AR
uv run jobbot linkedin sweep "enviar CV" --any-country
uv run jobbot linkedin sweep "enviar CV" --no-copy-links   # sin abrir el menú "…"
uv run jobbot linkedin sweep "enviar CV" --max-age-days 7
uv run jobbot linkedin sweep "enviar CV" --any-age
uv run jobbot jobs backfill-dates
uv run jobbot getonboard prepare              # refine acumulativo (default)
uv run jobbot getonboard prepare --seed old_gob.txt
uv run jobbot getonboard prepare --llm        # LangChain (uv sync --extra llm)
uv run jobbot getonboard prepare --cold       # solo si quieres partir de cero
uv run jobbot getonboard show-profile
uv run jobbot getonboard open-profile
uv run jobbot getonboard open-cvs
uv run jobbot getonboard upload-cv              # valida PDF (tamaño/magic/hash)
uv run jobbot getonboard upload-cv --apply --cdp http://127.0.0.1:9224  # sube + default
uv run jobbot getonboard sync --apply
uv run jobbot getonboard search                 # queries del perfil (profile queries)
uv run jobbot torre search [--remote]           # Torre (LATAM/remoto), API pública
uv run jobbot ops failures
uv run jobbot ops failure show F0001
uv run jobbot ops failure triage F0001 --status fixed
uv run jobbot ops failure issue F0001          # HITL → gh issue
uv run jobbot ops failure work F0001           # bash lane: issue→branch→PR→retry (#46)
uv run jobbot ops failure work F0001 --apply   # HITL: issue + fetch + checkout -b
uv run jobbot ops loop --cmd getonboard-prepare --interval 300
uv run jobbot portals list|add|detect
uv run jobbot portals form-learn URL --fetch          # qué pide un formulario (solo lee)
uv run jobbot portals form-learn URL --fixture page.html
uv run jobbot recruiters discover URL                 # prácticas públicas → candidatas
uv run jobbot recruiters list|show|promote|reject|export
uv run jobbot companies detect URL
uv run jobbot companies learn URL --company NAME --country CL
uv run jobbot companies list|show|promote|reject|sites|export
uv run jobbot companies discover data/companies-cl.example.yaml   # oneshot → candidatos
uv run jobbot companies import output/discovery/company_portals.generated.yaml
uv run jobbot companies signup NOMBRE --apply [--cdp URL] # fill known; HITL create (#44)
uv run jobbot companies recon NOMBRE --fixture PATH   # aprender ATS/form desde HTML (#45)
uv run jobbot companies recon NOMBRE --cdp URL --apply
uv run jobbot application apply J0001
uv run jobbot application apply J0001 --apply           # email: adapted CV attached in Gmail
uv run jobbot application apply --all                   # dry-run queue (#75)
uv run jobbot application check-answer J0001 -q "¿Por qué…?" --text "…"  # or --file (#159)
uv run jobbot application apply --all --apply --cdp http://127.0.0.1:9222
uv run jobbot browser sessions # preflight: ready | needs_login | unknown | profile_busy
uv run jobbot browser login            # permanentes + active + candidate; sin credenciales (#56)
uv run jobbot browser login --apply    # abre el siguiente portal sin sesión probada; tú entras
uv run jobbot secrets init             # vault local 0600 (opt-in; no inventa) (#157)
uv run jobbot secrets set indeed       # getpass; never argv
uv run jobbot secrets list             # sitios, sin valores
uv run jobbot browser chrome-debug --site gmail --port 9223
uv run jobbot application apply J0001 --apply --cdp http://127.0.0.1:9223
uv run jobbot profile suggest-from-market
uv run jobbot profile queries                   # búsquedas derivadas de la experiencia
uv run jobbot profile queries --apply           # confirma y guarda search_queries (editable)
uv run jobbot workspace list|new NAME|show|adopt
uv run jobbot --workspace NAME cv build --job J0001  # runs against a test CV
make site  # advisory page diagram from AtsKind/adapters/sources (stale = red suite)
```
