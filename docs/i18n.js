/* Site i18n — one dictionary, applied via data-i18n attributes. */
const SITE_STRINGS = {
en: {
  meta_title: "Nautilus Extensions — supercharge GNOME Files",
  meta_desc: "Productivity-focused Python extensions for Nautilus (GNOME Files): dual panel, folder colors, archive tools, PDF tools and more.",
  nav_install: "Install", nav_spotlight: "Folder Color", nav_ext: "Extensions",
  hero_title: 'Supercharge <span>GNOME Files</span>',
  hero_sub: "Productivity-focused Python extensions for <strong>Nautilus</strong> — dual panel, folder colorizer, archive browser, PDF tools, media helpers and more. Right where you need them: the context menu.",
  btn_start: "Get Started", btn_source: "View Source",
  install_h: "Install",
  install_p1: "Fedora / GNOME (Nautilus 46+, GTK4) — one line, no manual clone:",
  install_p2: "Or clone first:",
  spot_h: "🎨 Featured: Folder Color Revival + infinite colors",
  spot_p: 'The classic folder colorizer, revived for modern Nautilus — now with <strong>infinite custom colors</strong> powered by an embedded <a href="https://github.com/zonaro/NameToColor">NameToColor</a> engine (2254 named colors + pt-BR, deterministic hash for any word).',
  alt1: "red folder", alt2: "olive folder", alt3: "blue and white folder", alt4: "lime folder",
  feat1: "<strong>Custom color… dialog</strong> — type any name, hex or <code>rgb()</code>, with a live preview of your actual theme icon and a color picker per element.",
  feat2: "<strong>One or two colors</strong> (<code>name1;name2</code>) — back tab and front flap tinted independently; complex theme icons get one field per shape.",
  feat3: "<strong>Theme-aware</strong> — desaturates and tints your current theme's own folder icon (SVG or PNG); falls back gracefully.",
  feat4: "<strong>Built-ins unified</strong> — the 14 classic colors go through the exact same pipeline.",
  feat5: "Emblems, per-XDG special icons, restore-to-default, lazy theme loading.",
  ext_h: "All extensions",
  ext_p: "18 extensions, one install. Everything runs locally — no telemetry.",
  c1h: "🗂️ Dual Panel", c1p: "Double-pane manager inside Nautilus (F3), rsync progress, drag &amp; drop.",
  c2h: "🧭 Column Browser", c2p: "Miller-columns Finder-style browser (F9), threaded loading.",
  c3h: "⚙️ Extensions Manager", c3p: "Enable/disable extensions on the fly.",
  c4h: "🗜️ Archive Browser", c4p: "Browse, extract and create archives incl. multi-volume &amp; passwords (F7).",
  c5h: "📦 Extract Here", c5p: "One-click extraction with progress dialog.",
  c6h: "🎨 Annotate Image", c6p: "Arrows, shapes, text on PNG/JPG without GIMP.",
  c7h: "🗜️ Compress PDF", c7p: "Ghostscript presets with before/after sizes.",
  c8h: "🔗 Merge PDF", c8p: "Reorder pages and merge with drag &amp; drop.",
  c9h: "🔏 Watermark PDF", c9p: "Text/image watermarks with flattening.",
  c10h: "🔍 Preview Panel", c10p: "Side preview for images, video, PDF, text (F4).",
  c11h: "📦 Deb Installer", c11p: "Visual .deb installer with dependency check.",
  c12h: "🔎 Search &amp; Replace", c12p: "grep/ripgrep content search + replace with preview (F8).",
  c13h: "🎵 Video to Audio", c13p: "Batch extraction to MP3/M4A/OGG/OPUS/FLAC/WAV.",
  c14h: "⏱️ Duration Column", c14p: "Sortable HH:MM:SS column for audio/video.",
  c15h: "✂️ Cut Item Dimmer", c15p: "Dims Ctrl+X items so you don't forget them.",
  c16h: "✏️ Edit with Gedit", c16p: "One-click open text files in Gedit.",
  c17h: "📁 Folder Color Revival", c17p: "Color &amp; emblem tagging + infinite custom colors.",
  c18h: "👁️ Hidden Dim", c18p: "Dim hidden files' icons (or icon+label).",
  foot: 'Made with 💙 for Fedora &amp; GNOME · GPL-3.0 · <a href="https://github.com/zonaro/Nautilus-Extensions">zonaro/Nautilus-Extensions</a> (fork of <a href="https://github.com/ToFpon/Nautilus-Extensions">ToFpon/Nautilus-Extensions</a>)'
},
fr: {
  meta_title: "Nautilus Extensions — boostez GNOME Files",
  meta_desc: "Extensions Python productives pour Nautilus (GNOME Files) : double panneau, couleurs de dossiers, outils d'archives, outils PDF et plus.",
  nav_install: "Installer", nav_spotlight: "Couleur de dossier", nav_ext: "Extensions",
  hero_title: 'Boostez <span>GNOME Files</span>',
  hero_sub: "Des extensions Python axées productivité pour <strong>Nautilus</strong> — double panneau, coloration des dossiers, explorateur d'archives, outils PDF, helpers média et plus. Là où il faut : le menu contextuel.",
  btn_start: "Commencer", btn_source: "Voir le code",
  install_h: "Installer",
  install_p1: "Fedora / GNOME (Nautilus 46+, GTK4) — une ligne, sans clonage manuel :",
  install_p2: "Ou clonez d'abord :",
  spot_h: "🎨 En vedette : Folder Color Revival + couleurs infinies",
  spot_p: 'Le colorateur de dossiers classique, relancé pour Nautilus moderne — avec des <strong>couleurs personnalisées infinies</strong> grâce au moteur <a href="https://github.com/zonaro/NameToColor">NameToColor</a> intégré (2254 couleurs nommées + pt-BR, hachage déterministe pour tout mot).',
  alt1: "dossier rouge", alt2: "dossier olive", alt3: "dossier bleu et blanc", alt4: "dossier citron vert",
  feat1: "<strong>Dialogue Custom color…</strong> — saisissez un nom, un hex ou <code>rgb()</code>, avec aperçu en direct de votre icône de thème et un sélecteur par élément.",
  feat2: "<strong>Une ou deux couleurs</strong> (<code>nom1;nom2</code>) — onglet arrière et rabat avant teintés séparément ; les icônes complexes ont un champ par forme.",
  feat3: "<strong>Respect du thème</strong> — désature et teinte l'icône de dossier de votre thème (SVG ou PNG) ; repli gracieux.",
  feat4: "<strong>Unifié</strong> — les 14 couleurs classiques passent par le même pipeline.",
  feat5: "Emblèmes, icônes spéciales XDG, restauration, chargement paresseux du thème.",
  ext_h: "Toutes les extensions",
  ext_p: "18 extensions, une installation. Tout tourne en local — aucune télémétrie.",
  c1h: "🗂️ Double panneau", c1p: "Gestionnaire double panneau dans Nautilus (F3), progression rsync, glisser-déposer.",
  c2h: "🧭 Navigateur en colonnes", c2p: "Colonnes Miller style Finder (F9), chargement parallélisé.",
  c3h: "⚙️ Gestionnaire d'extensions", c3p: "Activez/désactivez les extensions à la volée.",
  c4h: "🗜️ Explorateur d'archives", c4p: "Naviguez, extrayez et créez des archives, multi-volumes et mots de passe (F7).",
  c5h: "📦 Extraire ici", c5p: "Extraction en un clic avec dialogue de progression.",
  c6h: "🎨 Annoter image", c6p: "Flèches, formes, texte sur PNG/JPG sans GIMP.",
  c7h: "🗜️ Compresser PDF", c7p: "Préréglages Ghostscript avec tailles avant/après.",
  c8h: "🔗 Fusionner PDF", c8p: "Réordonnez et fusionnez par glisser-déposer.",
  c9h: "🔏 Filigrane PDF", c9p: "Filigranes texte/image avec aplatissement.",
  c10h: "🔍 Panneau d'aperçu", c10p: "Aperçu latéral images, vidéo, PDF, texte (F4).",
  c11h: "📦 Installeur Deb", c11p: "Installeur .deb visuel avec vérification des dépendances.",
  c12h: "🔎 Rechercher &amp; remplacer", c12p: "Recherche grep/ripgrep + remplacement avec aperçu (F8).",
  c13h: "🎵 Vidéo vers audio", c13p: "Extraction par lots vers MP3/M4A/OGG/OPUS/FLAC/WAV.",
  c14h: "⏱️ Colonne durée", c14p: "Colonne HH:MM:SS triable pour audio/vidéo.",
  c15h: "✂️ Atténuer le couper", c15p: "Atténue les éléments Ctrl+X pour ne pas les oublier.",
  c16h: "✏️ Ouvrir dans Gedit", c16p: "Ouvrez les fichiers texte dans Gedit en un clic.",
  c17h: "📁 Folder Color Revival", c17p: "Étiquetage couleur &amp; emblèmes + couleurs infinies.",
  c18h: "👁️ Atténuer cachés", c18p: "Atténue les icônes (ou icône+label) des fichiers cachés.",
  foot: 'Fait avec 💙 pour Fedora &amp; GNOME · GPL-3.0 · <a href="https://github.com/zonaro/Nautilus-Extensions">zonaro/Nautilus-Extensions</a> (fork de <a href="https://github.com/ToFpon/Nautilus-Extensions">ToFpon/Nautilus-Extensions</a>)'
},
de: {
  meta_title: "Nautilus Extensions — GNOME-Dateien im Turbo",
  meta_desc: "Produktive Python-Erweiterungen für Nautilus (GNOME-Dateien): Doppelpanel, Ordnerfarben, Archiv-Werkzeuge, PDF-Werkzeuge und mehr.",
  nav_install: "Installation", nav_spotlight: "Ordnerfarbe", nav_ext: "Erweiterungen",
  hero_title: '<span>GNOME-Dateien</span> im Turbo',
  hero_sub: "Produktive Python-Erweiterungen für <strong>Nautilus</strong> — Doppelpanel, Ordnerfärbung, Archiv-Browser, PDF-Werkzeuge, Medienhelfer und mehr. Genau dort, wo man sie braucht: im Kontextmenü.",
  btn_start: "Los geht's", btn_source: "Quellcode ansehen",
  install_h: "Installation",
  install_p1: "Fedora / GNOME (Nautilus 46+, GTK4) — eine Zeile, kein manuelles Klonen:",
  install_p2: "Oder zuerst klonen:",
  spot_h: "🎨 Highlight: Folder Color Revival + unendliche Farben",
  spot_p: 'Der klassische Ordnerfärber, neu aufgelegt für modernes Nautilus — mit <strong>unendlichen benutzerdefinierten Farben</strong> dank eingebauter <a href="https://github.com/zonaro/NameToColor">NameToColor</a>-Engine (2254 benannte Farben + pt-BR, deterministischer Hash für jedes Wort).',
  alt1: "roter Ordner", alt2: "olivfarbener Ordner", alt3: "blau-weißer Ordner", alt4: "limettenfarbener Ordner",
  feat1: "<strong>Custom color…-Dialog</strong> — Namen, Hex oder <code>rgb()</code> eintippen, mit Live-Vorschau des eigenen Theme-Symbols und Farbwähler pro Element.",
  feat2: "<strong>Eine oder zwei Farben</strong> (<code>name1;name2</code>) — Rückseite und Vorderseite getrennt eingefärbt; komplexe Theme-Symbole bekommen ein Feld pro Form.",
  feat3: "<strong>Theme-bewusst</strong> — entsättigt und färbt das Ordnersymbol des aktuellen Themes (SVG oder PNG); mit Fallback.",
  feat4: "<strong>Vereinheitlicht</strong> — die 14 klassischen Farben laufen durch dieselbe Pipeline.",
  feat5: "Embleme, XDG-Spezialsymbole, Wiederherstellung, Lazy-Theme-Loading.",
  ext_h: "Alle Erweiterungen",
  ext_p: "18 Erweiterungen, eine Installation. Alles läuft lokal — keine Telemetrie.",
  c1h: "🗂️ Doppelpanel", c1p: "Zwei Panels in Nautilus (F3), rsync-Fortschritt, Drag &amp; Drop.",
  c2h: "🧭 Spaltenbrowser", c2p: "Miller-Spalten im Finder-Stil (F9), paralleles Laden.",
  c3h: "⚙️ Erweiterungsmanager", c3p: "Erweiterungen per Klick aktivieren/deaktivieren.",
  c4h: "🗜️ Archiv-Browser", c4p: "Archive durchsuchen, entpacken und erstellen inkl. Multi-Volume &amp; Passwörter (F7).",
  c5h: "📦 Hier entpacken", c5p: "Entpacken per Klick mit Fortschrittsdialog.",
  c6h: "🎨 Bild annotieren", c6p: "Pfeile, Formen, Text auf PNG/JPG ohne GIMP.",
  c7h: "🗜️ PDF komprimieren", c7p: "Ghostscript-Presets mit Vorher/Nachher-Größen.",
  c8h: "🔗 PDF zusammenführen", c8p: "Seiten per Drag &amp; Drop sortieren und vereinen.",
  c9h: "🔏 PDF-Wasserzeichen", c9p: "Text-/Bild-Wasserzeichen mit Flattening.",
  c10h: "🔍 Vorschau-Panel", c10p: "Seitenvorschau für Bilder, Video, PDF, Text (F4).",
  c11h: "📦 Deb-Installer", c11p: "Visueller .deb-Installer mit Abhängigkeitsprüfung.",
  c12h: "🔎 Suchen &amp; Ersetzen", c12p: "grep/ripgrep-Inhaltssuche + Ersetzen mit Vorschau (F8).",
  c13h: "🎵 Video zu Audio", c13p: "Stapelextraktion nach MP3/M4A/OGG/OPUS/FLAC/WAV.",
  c14h: "⏱️ Dauer-Spalte", c14p: "Sortierbare HH:MM:SS-Spalte für Audio/Video.",
  c15h: "✂️ Ausschneiden dimmen", c15p: "Dimmt Ctrl+X-Elemente, damit man sie nicht vergisst.",
  c16h: "✏️ In Gedit öffnen", c16p: "Textdateien per Klick in Gedit öffnen.",
  c17h: "📁 Folder Color Revival", c17p: "Farb- &amp; Emblem-Markierung + unendliche Farben.",
  c18h: "👁️ Versteckt dimmen", c18p: "Dimmt Symbole (oder Symbol+Label) versteckter Dateien.",
  foot: 'Mit 💙 für Fedora &amp; GNOME gemacht · GPL-3.0 · <a href="https://github.com/zonaro/Nautilus-Extensions">zonaro/Nautilus-Extensions</a> (Fork von <a href="https://github.com/ToFpon/Nautilus-Extensions">ToFpon/Nautilus-Extensions</a>)'
},
"pt-BR": {
  meta_title: "Nautilus Extensions — turbinando o GNOME Files",
  meta_desc: "Extensões Python de produtividade para o Nautilus (Arquivos do GNOME): painel duplo, cores de pastas, ferramentas de arquivos, ferramentas de PDF e mais.",
  nav_install: "Instalar", nav_spotlight: "Cor de pasta", nav_ext: "Extensões",
  hero_title: 'Turbinando o <span>GNOME Files</span>',
  hero_sub: "Extensões Python focadas em produtividade para o <strong>Nautilus</strong> — painel duplo, coloridor de pastas, navegador de arquivos compactados, ferramentas de PDF, helpers de mídia e mais. Bem onde você precisa: no menu de contexto.",
  btn_start: "Começar", btn_source: "Ver código",
  install_h: "Instalação",
  install_p1: "Fedora / GNOME (Nautilus 46+, GTK4) — uma linha, sem clonar manualmente:",
  install_p2: "Ou clone primeiro:",
  spot_h: "🎨 Destaque: Folder Color Revival + cores infinitas",
  spot_p: 'O clássico coloridor de pastas, revivido para o Nautilus moderno — agora com <strong>cores personalizadas infinitas</strong> graças ao motor <a href="https://github.com/zonaro/NameToColor">NameToColor</a> embutido (2254 cores nomeadas + pt-BR, hash determinístico para qualquer palavra).',
  alt1: "pasta vermelha", alt2: "pasta oliva", alt3: "pasta azul e branca", alt4: "pasta verde-limão",
  feat1: "<strong>Diálogo Custom color…</strong> — digite qualquer nome, hex ou <code>rgb()</code>, com pré-visualização ao vivo do ícone do seu tema e um seletor de cor por elemento.",
  feat2: "<strong>Uma ou duas cores</strong> (<code>nome1;nome2</code>) — aba traseira e aba frontal tingidas separadamente; ícones de temas complexos ganham um campo por forma.",
  feat3: "<strong>Consciente do tema</strong> — dessatura e tinge o ícone de pasta do seu tema atual (SVG ou PNG); com fallback elegante.",
  feat4: "<strong>Unificadas</strong> — as 14 cores clássicas passam pelo mesmo pipeline.",
  feat5: "Emblemas, ícones especiais XDG, restauração, carregamento preguiçoso do tema.",
  ext_h: "Todas as extensões",
  ext_p: "18 extensões, uma instalação. Tudo roda localmente — sem telemetria.",
  c1h: "🗂️ Painel duplo", c1p: "Gerenciador de painel duplo dentro do Nautilus (F3), progresso rsync, arrastar e soltar.",
  c2h: "🧭 Navegador em colunas", c2p: "Colunas Miller estilo Finder (F9), carregamento paralelizado.",
  c3h: "⚙️ Gerenciador de extensões", c3p: "Ative/desative extensões com um clique.",
  c4h: "🗜️ Navegador de arquivos", c4p: "Navegue, extraia e crie compactados, multi-volume e senhas (F7).",
  c5h: "📦 Extrair aqui", c5p: "Extração em um clique com diálogo de progresso.",
  c6h: "🎨 Anotar imagem", c6p: "Setas, formas e texto em PNG/JPG sem GIMP.",
  c7h: "🗜️ Comprimir PDF", c7p: "Predefinições Ghostscript com tamanhos antes/depois.",
  c8h: "🔗 Unir PDF", c8p: "Reordene e una com arrastar e soltar.",
  c9h: "🔏 Marca d'água em PDF", c9p: "Marcas de texto/imagem com flattening.",
  c10h: "🔍 Painel de prévia", c10p: "Prévia lateral de imagens, vídeo, PDF e texto (F4).",
  c11h: "📦 Instalador Deb", c11p: "Instalador .deb visual com checagem de dependências.",
  c12h: "🔎 Buscar &amp; substituir", c12p: "Busca grep/ripgrep + substituição com prévia (F8).",
  c13h: "🎵 Vídeo para áudio", c13p: "Extração em lote para MP3/M4A/OGG/OPUS/FLAC/WAV.",
  c14h: "⏱️ Coluna de duração", c14p: "Coluna HH:MM:SS ordenável para áudio/vídeo.",
  c15h: "✂️ Escurecer recorte", c15p: "Escurece itens Ctrl+X pra você não esquecer.",
  c16h: "✏️ Abrir no Gedit", c16p: "Abra textos no Gedit com um clique.",
  c17h: "📁 Folder Color Revival", c17p: "Marcação por cor e emblemas + cores infinitas.",
  c18h: "👁️ Escurecer ocultos", c18p: "Escurece ícones (ou ícone+rótulo) de arquivos ocultos.",
  foot: 'Feito com 💙 para Fedora &amp; GNOME · GPL-3.0 · <a href="https://github.com/zonaro/Nautilus-Extensions">zonaro/Nautilus-Extensions</a> (fork de <a href="https://github.com/ToFpon/Nautilus-Extensions">ToFpon/Nautilus-Extensions</a>)'
},
es: {
  meta_title: "Nautilus Extensions — potencia GNOME Files",
  meta_desc: "Extensiones Python de productividad para Nautilus (Archivos de GNOME): panel doble, colores de carpetas, herramientas de archivos, herramientas PDF y más.",
  nav_install: "Instalar", nav_spotlight: "Color de carpeta", nav_ext: "Extensiones",
  hero_title: 'Potencia <span>GNOME Files</span>',
  hero_sub: "Extensiones Python de productividad para <strong>Nautilus</strong> — panel doble, coloreador de carpetas, explorador de archivos, herramientas PDF, ayudantes multimedia y más. Justo donde las necesitas: en el menú contextual.",
  btn_start: "Empezar", btn_source: "Ver código",
  install_h: "Instalación",
  install_p1: "Fedora / GNOME (Nautilus 46+, GTK4) — una línea, sin clonar manualmente:",
  install_p2: "O clona primero:",
  spot_h: "🎨 Destacado: Folder Color Revival + colores infinitos",
  spot_p: 'El clásico coloreador de carpetas, revivido para Nautilus moderno — ahora con <strong>colores personalizados infinitos</strong> gracias al motor <a href="https://github.com/zonaro/NameToColor">NameToColor</a> integrado (2254 colores con nombre + pt-BR, hash determinista para cualquier palabra).',
  alt1: "carpeta roja", alt2: "carpeta oliva", alt3: "carpeta azul y blanca", alt4: "carpeta lima",
  feat1: "<strong>Diálogo Custom color…</strong> — escribe cualquier nombre, hex o <code>rgb()</code>, con vista previa en vivo del icono de tu tema y un selector por elemento.",
  feat2: "<strong>Uno o dos colores</strong> (<code>nombre1;nombre2</code>) — solapa trasera y frontal teñidas por separado; los iconos complejos tienen un campo por forma.",
  feat3: "<strong>Consciente del tema</strong> — desatura y tiñe el icono de carpeta de tu tema (SVG o PNG); con repliegue elegante.",
  feat4: "<strong>Unificado</strong> — los 14 colores clásicos pasan por el mismo pipeline.",
  feat5: "Emblemas, iconos especiales XDG, restauración, carga perezosa del tema.",
  ext_h: "Todas las extensiones",
  ext_p: "18 extensiones, una instalación. Todo funciona en local — sin telemetría.",
  c1h: "🗂️ Panel doble", c1p: "Gestor de doble panel en Nautilus (F3), progreso rsync, arrastrar y soltar.",
  c2h: "🧭 Navegador en columnas", c2p: "Columnas Miller estilo Finder (F9), carga paralelizada.",
  c3h: "⚙️ Gestor de extensiones", c3p: "Activa/desactiva extensiones con un clic.",
  c4h: "🗜️ Explorador de archivos", c4p: "Explora, extrae y crea archivos, multivolumen y contraseñas (F7).",
  c5h: "📦 Extraer aquí", c5p: "Extracción en un clic con diálogo de progreso.",
  c6h: "🎨 Anotar imagen", c6p: "Flechas, formas y texto en PNG/JPG sin GIMP.",
  c7h: "🗜️ Comprimir PDF", c7p: "Preajustes Ghostscript con tamaños antes/después.",
  c8h: "🔗 Unir PDF", c8p: "Reordena y fusiona con arrastrar y soltar.",
  c9h: "🔏 Marca de agua en PDF", c9p: "Marcas de texto/imagen con aplanado.",
  c10h: "🔍 Panel de vista previa", c10p: "Vista previa lateral de imágenes, vídeo, PDF y texto (F4).",
  c11h: "📦 Instalador Deb", c11p: "Instalador .deb visual con comprobación de dependencias.",
  c12h: "🔎 Buscar &amp; reemplazar", c12p: "Búsqueda grep/ripgrep + reemplazo con vista previa (F8).",
  c13h: "🎵 Vídeo a audio", c13p: "Extracción por lotes a MP3/M4A/OGG/OPUS/FLAC/WAV.",
  c14h: "⏱️ Columna de duración", c14p: "Columna HH:MM:SS ordenable para audio/vídeo.",
  c15h: "✂️ Atenuar recorte", c15p: "Atenúa los elementos Ctrl+X para no olvidarlos.",
  c16h: "✏️ Abrir en Gedit", c16p: "Abre textos en Gedit con un clic.",
  c17h: "📁 Folder Color Revival", c17p: "Marcado por color y emblemas + colores infinitos.",
  c18h: "👁️ Atenuar ocultos", c18p: "Atenúa iconos (o icono+etiqueta) de archivos ocultos.",
  foot: 'Hecho con 💙 para Fedora y GNOME · GPL-3.0 · <a href="https://github.com/zonaro/Nautilus-Extensions">zonaro/Nautilus-Extensions</a> (fork de <a href="https://github.com/ToFpon/Nautilus-Extensions">ToFpon/Nautilus-Extensions</a>)'
}
};

const SITE_LANGS = ["en", "fr", "de", "pt-BR", "es"];
const SITE_LABELS = { en: "EN", fr: "FR", de: "DE", "pt-BR": "PT-BR", es: "ES" };

function siteLang(defaultLang) {
  try {
    const saved = localStorage.getItem("site-lang");
    if (saved && SITE_STRINGS[saved]) return saved;
  } catch (e) { /* private mode */ }
  const nav = (navigator.language || "en").toLowerCase();
  if (nav.startsWith("pt")) return "pt-BR";
  for (const l of SITE_LANGS) {
    if (nav === l.toLowerCase() || nav.startsWith(l.toLowerCase() + "-")) return l;
  }
  return defaultLang || "en";
}

function setSiteLang(lang) {
  if (!SITE_STRINGS[lang]) lang = "en";
  const dict = SITE_STRINGS[lang];
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (key in dict) el.innerHTML = dict[key];
  });
  document.querySelectorAll("[data-i18n-alt]").forEach((el) => {
    const key = el.getAttribute("data-i18n-alt");
    if (key in dict) el.setAttribute("alt", dict[key]);
  });
  document.querySelectorAll("[data-i18n-content]").forEach((el) => {
    const key = el.getAttribute("data-i18n-content");
    if (key in dict) el.setAttribute("content", dict[key]);
  });
  document.querySelectorAll("[data-lang]").forEach((el) => {
    if (el.getAttribute("data-lang") === lang) el.classList.add("active");
    else el.classList.remove("active");
  });
  try { localStorage.setItem("site-lang", lang); } catch (e) { /* private mode */ }
}
