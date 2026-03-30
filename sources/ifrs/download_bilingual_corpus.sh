#!/usr/bin/env bash
# Download bilingual IFRS corpus — full consolidated financial statements with notes
# Usage: bash sources/ifrs/download_bilingual_corpus.sh [lang_code]
# Example: bash sources/ifrs/download_bilingual_corpus.sh de   # download only German pairs
#          bash sources/ifrs/download_bilingual_corpus.sh       # download all

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FILTER_LANG="${1:-all}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

download() {
  local lang="$1" file="$2" url="$3"
  local dir="${SCRIPT_DIR}/${lang}"
  local path="${dir}/${file}"

  if [[ "$FILTER_LANG" != "all" && "$FILTER_LANG" != "$lang" ]]; then
    return 0
  fi

  mkdir -p "$dir"

  if [[ -f "$path" ]]; then
    echo -e "${YELLOW}SKIP${NC} ${lang}/${file} (exists)"
    return 0
  fi

  echo -n "Downloading ${lang}/${file} ... "
  if curl -sfL --max-time 120 -o "$path" "$url"; then
    # Verify it's actually a PDF (not an HTML error page)
    if file "$path" | grep -q "PDF"; then
      local size=$(du -h "$path" | cut -f1)
      echo -e "${GREEN}OK${NC} (${size})"
    else
      echo -e "${RED}FAIL${NC} (not a PDF — likely redirect/error page)"
      rm -f "$path"
    fi
  else
    echo -e "${RED}FAIL${NC} (curl error)"
    rm -f "$path"
  fi
}

manual_note() {
  local lang="$1" file="$2" ir_url="$3" note="$4"
  if [[ "$FILTER_LANG" != "all" && "$FILTER_LANG" != "$lang" ]]; then
    return 0
  fi
  local dir="${SCRIPT_DIR}/${lang}"
  local path="${dir}/${file}"
  mkdir -p "$dir"
  if [[ -f "$path" ]]; then
    echo -e "${YELLOW}SKIP${NC} ${lang}/${file} (exists)"
  else
    echo -e "${RED}MANUAL${NC} ${lang}/${file}"
    echo "         IR page: ${ir_url}"
    echo "         Note: ${note}"
  fi
}

echo "=== FOBE Bilingual IFRS Corpus Downloader ==="
echo "Target: sources/ifrs/{lang}/"
echo ""

# ─────────────────────────────────────────────────────────────
# GERMAN (DE) — large caps — 9 companies × 2 languages = 18 PDFs
# ─────────────────────────────────────────────────────────────
echo "── DE (German — large caps) ──"

# Deutsche Bank
manual_note de "deutsche_bank_ifrs_2024_en.pdf" \
  "https://investor-relations.db.com/reports-and-events/annual-reports/" \
  "Download 'Annual Report 2024' PDF — full consolidated IFRS with notes"
manual_note de "deutsche_bank_ifrs_2024_de.pdf" \
  "https://investor-relations.db.com/reports-and-events/annual-reports/" \
  "Download 'Geschäftsbericht 2024' PDF"

# Allianz
manual_note de "allianz_ifrs_2024_en.pdf" \
  "https://www.allianz.com/en/investor_relations/results-reports/annual-reports.html" \
  "Download 'Group Annual Report 2024' PDF (EN)"
manual_note de "allianz_ifrs_2024_de.pdf" \
  "https://www.allianz.com/en/investor_relations/results-reports/annual-reports.html" \
  "Download 'Geschäftsbericht 2024' PDF (DE)"

# K+S
manual_note de "ks_ifrs_2024_en.pdf" \
  "https://www.kpluss.com/en-us/investors/reports-and-presentations/" \
  "Download 'Annual Report 2024' PDF"
manual_note de "ks_ifrs_2024_de.pdf" \
  "https://www.kpluss.com/en-us/investors/reports-and-presentations/" \
  "Download 'Geschäftsbericht 2024' PDF"

# Wintershall Dea (2023 — acquired by Harbour in 2024)
manual_note de "wintershall_dea_ifrs_2023_en.pdf" \
  "https://wintershalldea.com/en/investor-relations/reports-and-presentations" \
  "FY2023 — last available. May need Wayback Machine or Bundesanzeiger"
manual_note de "wintershall_dea_ifrs_2023_de.pdf" \
  "https://wintershalldea.com/en/investor-relations/reports-and-presentations" \
  "FY2023 Geschäftsbericht — try Bundesanzeiger as fallback"

# METRO (FY ends Sep 30)
manual_note de "metro_ifrs_2024_en.pdf" \
  "https://www.metroag.de/en/investors/publications" \
  "Download 'Annual Report FY 2023/24' PDF"
manual_note de "metro_ifrs_2024_de.pdf" \
  "https://www.metroag.de/en/investors/publications" \
  "Download 'Geschäftsbericht GJ 2023/24' PDF"

# SAP
manual_note de "sap_ifrs_2024_en.pdf" \
  "https://www.sap.com/investors/en/reports.html" \
  "Download 'SAP Integrated Report 2024' (EN) — contains full IFRS consolidated FS"
manual_note de "sap_ifrs_2024_de.pdf" \
  "https://www.sap.com/investors/en/reports.html" \
  "Download 'SAP Integrierter Bericht 2024' (DE)"

# Deutsche Telekom
manual_note de "deutsche_telekom_ifrs_2024_en.pdf" \
  "https://www.telekom.com/en/investor-relations/publications/financial-results" \
  "Download 'Annual Report 2024' PDF"
manual_note de "deutsche_telekom_ifrs_2024_de.pdf" \
  "https://www.telekom.com/en/investor-relations/publications/financial-results" \
  "Download 'Geschäftsbericht 2024' PDF"

# Siemens (FY ends Sep 30)
manual_note de "siemens_ifrs_2024_en.pdf" \
  "https://www.siemens.com/global/en/company/investor-relations/events-publications-ad-hoc/annualreports.html" \
  "Download 'Annual Report FY 2024' PDF — uses UUID URLs, must visit IR page"
manual_note de "siemens_ifrs_2024_de.pdf" \
  "https://www.siemens.com/global/en/company/investor-relations/events-publications-ad-hoc/annualreports.html" \
  "Download 'Geschäftsbericht GJ 2024' PDF"

# Bayer
manual_note de "bayer_ifrs_2024_en.pdf" \
  "https://www.bayer.com/en/investors/reports" \
  "Download 'Annual Report 2024' PDF"
manual_note de "bayer_ifrs_2024_de.pdf" \
  "https://www.bayer.com/en/investors/reports" \
  "Download 'Geschäftsbericht 2024' PDF"

echo ""

# ─────────────────────────────────────────────────────────────
# GERMAN (DE) — DACH mid-caps — 20 companies × 2 languages = 40 PDFs
# ─────────────────────────────────────────────────────────────
echo "── DE (German — mid-caps) ──"

# Fresenius SE
download de "fresenius_ifrs_2024_en.pdf" \
  "https://www.fresenius.com/sites/default/files/2025-03/Fresenius_Annual_Report_2024.pdf"
download de "fresenius_ifrs_2024_de.pdf" \
  "https://www.fresenius.com/sites/default/files/2025-03/Fresenius_Geschaeftsbericht_2024.pdf"

# Fresenius Medical Care
download de "fresenius_medical_care_ifrs_2024_en.pdf" \
  "https://freseniusmedicalcare.com/content/dam/fresenius-medical-care/global/en/04_media/pdf/publications/2024/FME_Annual_Report_2024_EN.pdf"
download de "fresenius_medical_care_ifrs_2024_de.pdf" \
  "https://freseniusmedicalcare.com/content/dam/fresenius-medical-care/global/en/04_media/pdf/publications/2024/FME_Geschaeftsbericht_2024_DE.pdf"

# Hannover Re
download de "hannover_re_ifrs_2024_en.pdf" \
  "https://assets.hannover-re.com/asset/533267266226/document_53ot0hkto941vdmthk246os532/2024_HRSE_e.pdf"
download de "hannover_re_ifrs_2024_de.pdf" \
  "https://assets.hannover-re.com/asset/533267266226/document_jaieng01c51k1bgh7b536kf63s/2024_GBKonzern_d.pdf"

# Sartorius
download de "sartorius_ifrs_2024_en.pdf" \
  "https://www.sartorius.com/download/1661808/fy-2024-download-sag-annual-report-en-data.pdf"
download de "sartorius_ifrs_2024_de.pdf" \
  "https://www.sartorius.com/download/1661828/fy-2024-download-sag-annual-report-2024-de-data.pdf"

# Symrise
manual_note de "symrise_ifrs_2024_en.pdf" \
  "https://www.symrise.com/investors/downloads/" \
  "Download 'Annual Report 2024' (EN) or consolidated FS extract"
manual_note de "symrise_ifrs_2024_de.pdf" \
  "https://www.symrise.com/investors/downloads/" \
  "Download 'Geschäftsbericht 2024' (DE)"

# Lanxess
download de "lanxess_ifrs_2024_en.pdf" \
  "https://lanxess.com/-/media/project/lanxess/corporate-internet/investors/reporting/2024/lxs_ar-2024_en_web.pdf"
manual_note de "lanxess_ifrs_2024_de.pdf" \
  "https://lanxess.com/en/investors/reporting" \
  "Download 'Geschäftsbericht 2024' (DE)"

# GEA Group
download de "gea_group_ifrs_2024_en.pdf" \
  "https://cdn.gea.com/-/media/investors/annual-report/2024/annual-report-2024-en.pdf"
download de "gea_group_ifrs_2024_de.pdf" \
  "https://cdn.gea.com/-/media/investors/annual-report/2024/annual-report-2024-de.pdf"

# Kion Group
download de "kion_group_ifrs_2024_en.pdf" \
  "https://www.kiongroup.com/KION-Website-Main/Investor-Relations/Reports-Presentations/2024-Reports-Presentations/Q4-FY-2024/2024-Q4_Annual_Report_KION_Group.pdf"
download de "kion_group_ifrs_2024_de.pdf" \
  "https://www.kiongroup.com/KION-Website-Main/Investor-Relations/Reports-Presentations/2024-Reports-Presentations/Q4-FY-2024/2024-Q4_Geschaeftsbericht_KION_Group.pdf"

# Hugo Boss
manual_note de "hugo_boss_ifrs_2024_en.pdf" \
  "https://group.hugoboss.com/en/investors/publications" \
  "Download 'Annual Report 2024' (EN)"
manual_note de "hugo_boss_ifrs_2024_de.pdf" \
  "https://group.hugoboss.com/en/investors/publications" \
  "Download 'Geschäftsbericht 2024' (DE) — try annualreport.hugoboss.com/2024 language switcher"

# Puma
download de "puma_ifrs_2024_en.pdf" \
  "https://about.puma.com/sites/default/files/financial-report/2024/puma-annual-report-2024-en-final.pdf"
download de "puma_ifrs_2024_de.pdf" \
  "https://about.puma.com/sites/default/files/financial-report/2024/puma-geschaeftsbericht-2024-de-final.pdf"

# Knorr-Bremse
manual_note de "knorr_bremse_ifrs_2024_en.pdf" \
  "https://ir.knorr-bremse.com/en/financial-publications-presentations" \
  "Download 'Annual Report 2024' (EN)"
manual_note de "knorr_bremse_ifrs_2024_de.pdf" \
  "https://ir.knorr-bremse.com/en/financial-publications-presentations" \
  "Download 'Geschäftsbericht 2024' (DE)"

# MTU Aero Engines
download de "mtu_aero_engines_ifrs_2024_en.pdf" \
  "https://www.mtu.de/fileadmin/DE/5_Investoren/Financial_Report/MTUAeroEnginesAG_AnnualReport_2024_en_locked.pdf"
download de "mtu_aero_engines_ifrs_2024_de.pdf" \
  "https://www.mtu.de/fileadmin/DE/5_Investoren/Financial_Report/MTUAeroEnginesAG_Geschaeftsbericht_2024_de_locked.pdf"

# Wacker Chemie
download de "wacker_chemie_ifrs_2024_en.pdf" \
  "https://reports.wacker.com/2024/annual-report/_assets/downloads/entire-wacker-ar24.pdf"
manual_note de "wacker_chemie_ifrs_2024_de.pdf" \
  "https://www.wacker.com/cms/en-us/investor-relations/financial-reports/financial-reports-overview.html" \
  "Download 'Geschäftsbericht 2024' (DE)"

# Evonik Industries
download de "evonik_ifrs_2024_en.pdf" \
  "https://www.evonik.com/content/dam/evonik/documents/Evonik_Financial_and_Sustainability_Report_2024.pdf.coredownload.pdf"
download de "evonik_ifrs_2024_de.pdf" \
  "https://www.evonik.com/content/dam/evonik/documents/Evonik_Finanz_und_Nachhaltigkeitsbericht_2024.pdf.coredownload.pdf"

# Dürr AG
download de "duerr_ifrs_2024_en.pdf" \
  "https://www.durr-group.com/fileadmin/durr-group.com/Investors/Downloads/Reports/2024/annual-report-2024-EN.pdf"
download de "duerr_ifrs_2024_de.pdf" \
  "https://www.durr-group.com/fileadmin/durr-group.com/Investors/Downloads/Reports/2024/annual-report-2024-DE.pdf"

# Aurubis (FY Oct–Sep, FY2024/25)
download de "aurubis_ifrs_2025_en.pdf" \
  "https://annualreport2024-25.aurubis.com/fileadmin/static/pdf_en/Aurubis-AR-24-25-Consolidated-Financial-Statements.pdf"
download de "aurubis_ifrs_2025_de.pdf" \
  "https://geschaeftsbericht2024-25.aurubis.com/fileadmin/static/pdf_de/Aurubis-GB-24-25-Konzernabschluss.pdf"

# Bilfinger
download de "bilfinger_ifrs_2024_en.pdf" \
  "https://www.bilfinger.com/fileadmin/One_Global_Website/Investors/IRgemListe/Publikationen/Quartalsberichtserstattung/2024/Q4/GB24_e_gesamt.pdf"
download de "bilfinger_ifrs_2024_de.pdf" \
  "https://www.bilfinger.com/fileadmin/One_Global_Website/Investors/IRgemListe/Publikationen/Quartalsberichtserstattung/2024/Q4/GB24_d_gesamt.pdf"

# Gerresheimer (FY ends Nov 30)
download de "gerresheimer_ifrs_2024_en.pdf" \
  "https://www.gerresheimer.com/fileadmin/user_upload/user_upload/gerresheimer/ir/downloads/annual-report/24/Downloads/Annual_Report/Gerresheimer_Annual_Report_2024_en_protected.pdf"
download de "gerresheimer_ifrs_2024_de.pdf" \
  "https://www.gerresheimer.com/fileadmin/user_upload/user_upload/gerresheimer/ir/downloads/annual-report/24/Downloads/Annual_Report/Gerresheimer_Geschaeftsbericht_2024_de_geschuetzt.pdf"

# Scout24
manual_note de "scout24_ifrs_2024_en.pdf" \
  "https://www.scout24.com/en/investor-relations/financial-reports-presentations" \
  "Download 'Annual Report 2024' (EN)"
manual_note de "scout24_ifrs_2024_de.pdf" \
  "https://www.scout24.com/en/investor-relations/financial-reports-presentations" \
  "Download 'Geschäftsbericht 2024' (DE)"

# Rheinmetall
manual_note de "rheinmetall_ifrs_2024_en.pdf" \
  "https://ir.rheinmetall.com/investor-relations/news/financial-reports" \
  "Download 'Annual Report 2024' (EN)"
manual_note de "rheinmetall_ifrs_2024_de.pdf" \
  "https://ir.rheinmetall.com/investor-relations/news/financial-reports" \
  "Download 'Geschäftsbericht 2024' (DE)"

# --- DE additional mid-caps ---

# Brenntag
manual_note de "brenntag_ifrs_2024_en.pdf" \
  "https://www.brenntag.com/en-de/investor-relations/reports-and-presentations/" \
  "Download 'Annual Report 2024' (EN)"
manual_note de "brenntag_ifrs_2024_de.pdf" \
  "https://www.brenntag.com/en-de/investor-relations/reports-and-presentations/" \
  "Download 'Geschäftsbericht 2024' (DE)"

# Covestro
manual_note de "covestro_ifrs_2024_en.pdf" \
  "https://www.covestro.com/en/investor-relations/financial-reports" \
  "Download 'Annual Report 2024' (EN)"
manual_note de "covestro_ifrs_2024_de.pdf" \
  "https://www.covestro.com/en/investor-relations/financial-reports" \
  "Download 'Geschäftsbericht 2024' (DE)"

# Jungheinrich
manual_note de "jungheinrich_ifrs_2024_en.pdf" \
  "https://www.jungheinrich.com/investor-relations/berichte-und-praesentationen" \
  "Download 'Annual Report 2024' (EN)"
manual_note de "jungheinrich_ifrs_2024_de.pdf" \
  "https://www.jungheinrich.com/investor-relations/berichte-und-praesentationen" \
  "Download 'Geschäftsbericht 2024' (DE)"

# DMG MORI
manual_note de "dmg_mori_ifrs_2024_en.pdf" \
  "https://www.dmgmori-ag.com/en/investor-relations/reports" \
  "Download 'Annual Report 2024' (EN)"
manual_note de "dmg_mori_ifrs_2024_de.pdf" \
  "https://www.dmgmori-ag.com/en/investor-relations/reports" \
  "Download 'Geschäftsbericht 2024' (DE)"

# Bechtle
manual_note de "bechtle_ifrs_2024_en.pdf" \
  "https://www.bechtle.com/investor-relations/reports" \
  "Download 'Annual Report 2024' (EN)"
manual_note de "bechtle_ifrs_2024_de.pdf" \
  "https://www.bechtle.com/investor-relations/reports" \
  "Download 'Geschäftsbericht 2024' (DE)"

# ATOSS Software
manual_note de "atoss_ifrs_2024_en.pdf" \
  "https://www.atoss.com/en/investor-relations/reports-and-publications" \
  "Download 'Annual Report 2024' (EN)"
manual_note de "atoss_ifrs_2024_de.pdf" \
  "https://www.atoss.com/en/investor-relations/reports-and-publications" \
  "Download 'Geschäftsbericht 2024' (DE)"

# Carl Zeiss Meditec
manual_note de "carl_zeiss_meditec_ifrs_2024_en.pdf" \
  "https://www.zeiss.com/meditec-ag/investor-relations/publications.html" \
  "Download 'Annual Report 2024' (EN)"
manual_note de "carl_zeiss_meditec_ifrs_2024_de.pdf" \
  "https://www.zeiss.com/meditec-ag/investor-relations/publications.html" \
  "Download 'Geschäftsbericht 2024' (DE)"

# Evotec
manual_note de "evotec_ifrs_2024_en.pdf" \
  "https://www.evotec.com/en/investor-relations/financial-reports" \
  "Download 'Annual Report 2024' (EN)"
manual_note de "evotec_ifrs_2024_de.pdf" \
  "https://www.evotec.com/en/investor-relations/financial-reports" \
  "Download 'Geschäftsbericht 2024' (DE)"

# Fraport
manual_note de "fraport_ifrs_2024_en.pdf" \
  "https://www.fraport.com/en/investors/publications-and-events.html" \
  "Download 'Annual Report 2024' (EN)"
manual_note de "fraport_ifrs_2024_de.pdf" \
  "https://www.fraport.com/en/investors/publications-and-events.html" \
  "Download 'Geschäftsbericht 2024' (DE)"

# Hapag-Lloyd
manual_note de "hapag_lloyd_ifrs_2024_en.pdf" \
  "https://www.hapag-lloyd.com/en/ir/publications/financial-reports.html" \
  "Download 'Annual Report 2024' (EN)"
manual_note de "hapag_lloyd_ifrs_2024_de.pdf" \
  "https://www.hapag-lloyd.com/en/ir/publications/financial-reports.html" \
  "Download 'Geschäftsbericht 2024' (DE)"

# TAG Immobilien
manual_note de "tag_immobilien_ifrs_2024_en.pdf" \
  "https://www.tag-ag.com/investor-relations/reports-presentations" \
  "Download 'Annual Report 2024' (EN)"
manual_note de "tag_immobilien_ifrs_2024_de.pdf" \
  "https://www.tag-ag.com/investor-relations/reports-presentations" \
  "Download 'Geschäftsbericht 2024' (DE)"

# ProSiebenSat.1
manual_note de "prosiebensat1_ifrs_2024_en.pdf" \
  "https://www.prosiebensat1.com/en/investor-relations/publications/annual-reports" \
  "Download 'Annual Report 2024' (EN)"
manual_note de "prosiebensat1_ifrs_2024_de.pdf" \
  "https://www.prosiebensat1.com/en/investor-relations/publications/annual-reports" \
  "Download 'Geschäftsbericht 2024' (DE)"

# Forvia HELLA
manual_note de "hella_ifrs_2024_en.pdf" \
  "https://www.hella.com/hella-com/en/Investor-Relations.html" \
  "Download 'Annual Report 2024' (EN)"
manual_note de "hella_ifrs_2024_de.pdf" \
  "https://www.hella.com/hella-com/en/Investor-Relations.html" \
  "Download 'Geschäftsbericht 2024' (DE)"

echo ""

# ─────────────────────────────────────────────────────────────
# SWISS (CH) — 15 companies × 2 languages = 30 PDFs
# ─────────────────────────────────────────────────────────────
echo "── CH (Swiss) ──"

# Schindler Group
download ch "schindler_ifrs_2024_en.pdf" \
  "https://group.schindler.com/content/dam/website/group/docs/investors/2024/2024-schindler-fy-financial-statements-en.pdf/_jcr_content/renditions/original./2024-schindler-fy-financial-statements-en.pdf"
download ch "schindler_ifrs_2024_de.pdf" \
  "https://group.schindler.com/content/dam/website/group/docs/investors/2024/2024-schindler-fy-financial-statements-de.pdf/_jcr_content/renditions/original./2024-schindler-fy-financial-statements-de.pdf"

# Georg Fischer (GF)
download ch "georg_fischer_ifrs_2024_en.pdf" \
  "https://www.georgfischer.com/content/dam/commonassets/corp/documents/reports/annual-report/annual-report-2024/en/annual-report-2024-full-version-en.pdf"
manual_note ch "georg_fischer_ifrs_2024_de.pdf" \
  "https://www.georgfischer.com/en/investors/reports-and-presentations.html" \
  "Download 'Geschäftsbericht 2024 Vollversion' (DE)"

# Sulzer
download ch "sulzer_ifrs_2024_en.pdf" \
  "https://www.sulzer.com/en/-/media/files/about-us/investors/financial_reporting/2024_annual_results/sulzer_annual_report_2024.pdf"
download ch "sulzer_ifrs_2024_de.pdf" \
  "https://report.sulzer.com/ar24/app/uploads/Sulzer_Geschaftsbericht_2024.pdf"

# Autoneum
download ch "autoneum_ifrs_2024_en.pdf" \
  "https://www.autoneum.com/wp-content/uploads/2025/03/ATN_Annual-Report_2024.pdf"
download ch "autoneum_ifrs_2024_de.pdf" \
  "https://www.autoneum.com/wp-content/uploads/2025/03/ATN_Geschaeftsbericht_2024.pdf"

# SFS Group
download ch "sfs_group_ifrs_2024_en.pdf" \
  "https://www.sfs.com/downloads/investor-relations/publications/annual-report-2024.pdf"
download ch "sfs_group_ifrs_2024_de.pdf" \
  "https://www.sfs.com/downloads/investor-relations/publikationen/annual-report-2024.pdf"

# Bucher Industries
manual_note ch "bucher_industries_ifrs_2024_en.pdf" \
  "https://www.bucherindustries.com/en/investors/financial-reports" \
  "Download 'Annual Report 2024' (EN) — token-based download URL"
manual_note ch "bucher_industries_ifrs_2024_de.pdf" \
  "https://www.bucherindustries.com/de/investoren/finanzberichte" \
  "Download 'Geschäftsbericht 2024' (DE) — token-based download URL"

# OC Oerlikon
download ch "oerlikon_ifrs_2024_en.pdf" \
  "https://www.oerlikon.com/ecoma/files/Oerlikon_Annual_Report_2024.pdf?download=true"
manual_note ch "oerlikon_ifrs_2024_de.pdf" \
  "https://www.oerlikon.com/en/investors/reports-publications/" \
  "Download 'Geschäftsbericht 2024' (DE)"

# Dätwyler
manual_note ch "datwyler_ifrs_2024_en.pdf" \
  "https://datwyler.com/media/reporting/annual-report/2024" \
  "Download 'Financial Report 2024' (EN)"
manual_note ch "datwyler_ifrs_2024_de.pdf" \
  "https://datwyler.com/de/media/reporting/annual-report/2024" \
  "Download 'Finanzbericht 2024' (DE)"

# Interroll
download ch "interroll_ifrs_2024_en.pdf" \
  "https://ir-interroll-prod.fra1.cdn.digitaloceanspaces.com/files/Reporting/Annual-Report-2024/PDF/Interroll-Annual-Report-2024.pdf"
manual_note ch "interroll_ifrs_2024_de.pdf" \
  "https://www.interroll.com/de/unternehmen/investoren/berichte-publikationen" \
  "Download 'Geschäftsbericht 2024' (DE)"

# Ems-Chemie (FY May–Apr)
manual_note ch "ems_chemie_ifrs_2024_en.pdf" \
  "https://www.ems-group.com/en/investors/financial-/-media-information/business-/-financial-reports/" \
  "Download '62nd Annual Report FY 2024/2025' (EN)"
manual_note ch "ems_chemie_ifrs_2024_de.pdf" \
  "https://www.ems-group.com/en/investors/financial-/-media-information/business-/-financial-reports/" \
  "Download 'Geschäftsbericht 2024/2025' (DE)"

# Landis+Gyr
download ch "landis_gyr_ifrs_2024_en.pdf" \
  "https://www.landisgyr.com/webfoo/wp-content/uploads/2025/05/Landis_Gyr_Annual_Report_2024_EN_Full.pdf"
manual_note ch "landis_gyr_ifrs_2024_de.pdf" \
  "https://www.landisgyr.eu/investors/publication-downloads/" \
  "Download 'Geschäftsbericht 2024' (DE)"

# Belimo
download ch "belimo_ifrs_2024_en.pdf" \
  "https://www.belimo.com/mam/corporate-communications/investor-relations/Reports%20and%20Presentations/2025_03_Annual_Report_2024_EN.pdf"
manual_note ch "belimo_ifrs_2024_de.pdf" \
  "https://report.belimo.com/ar24/en/download-center" \
  "Download annual report DE extract (note: full report is EN-primary)"

# Zehnder Group
download ch "zehnder_ifrs_2024_en.pdf" \
  "https://report.zehndergroup.com/2024/app/uploads/zehnder_group_annual_report_2024_en.pdf"
manual_note ch "zehnder_ifrs_2024_de.pdf" \
  "https://www.zehndergroup.com/en/investor-relations/reports-presentations" \
  "Download Management Report (DE) — full report is EN-primary"

# Comet Holding
manual_note ch "comet_ifrs_2024_en.pdf" \
  "https://comet.tech/en/investors/downloads/reports-and-presentations" \
  "Download 'Annual Report 2024' (EN)"
manual_note ch "comet_ifrs_2024_de.pdf" \
  "https://comet.tech/en/investors/downloads/reports-and-presentations" \
  "Download 'Geschäftsbericht 2024' (DE) — verify DE availability"

echo ""

# ─────────────────────────────────────────────────────────────
# AUSTRIAN (AT) — 15 companies × 2 languages = 30 PDFs
# ─────────────────────────────────────────────────────────────
echo "── AT (Austrian — mid-caps) ──"

# Verbund AG
download at "verbund_ifrs_2024_en.pdf" \
  "https://www.verbund.com/media/knlh3iey/verbund-integrated-annual-report-2024-englisch-final-1.pdf"
download at "verbund_ifrs_2024_de.pdf" \
  "https://www.verbund.com/media/aqdgfhra/verbund-integrierter-geschaeftsbericht-2024-deutsch-final.pdf"

# Erste Group Bank
download at "erste_group_ifrs_2024_en.pdf" \
  "https://cdn0.erstegroup.com/content/dam/at/eh/www_erstegroup_com/en/Investor_Relations/onlinear2024/ar24reports/AR2024_FINAL_en.pdf"
download at "erste_group_ifrs_2024_de.pdf" \
  "https://cdn0.erstegroup.com/content/dam/at/eh/www_erstegroup_com/de/ir/onlinegb2024/gb24berichte/GB2024_FINAL_de.pdf"

# UNIQA Insurance Group
download at "uniqa_ifrs_2024_en.pdf" \
  "https://www.uniqagroup.com/grp/investor-relations/publications/UNIQA_Group_Report_2024.pdf"
download at "uniqa_ifrs_2024_de.pdf" \
  "https://www.uniqagroup.com/grp/investor-relations/publications/UNIQA_Konzernbericht_2024.pdf"

# Österreichische Post AG
download at "post_ag_ifrs_2024_en.pdf" \
  "https://assets.post.at/-/media/Dokumente/En/Investor-Relations/Geschaefts--und-Nachhaltigkeitsberichte/Austrian-Post-Annual-Report-2024.pdf"
manual_note at "post_ag_ifrs_2024_de.pdf" \
  "https://www.post.at/ir/c/geschaeftsberichte" \
  "Download 'Geschäftsbericht 2024' (DE)"

# A1 Group / Telekom Austria
download at "a1_group_ifrs_2024_en.pdf" \
  "https://a1.group/wp-content/uploads/sites/6/2025/04/AnnualFinancialReport_2024_EN.pdf"
manual_note at "a1_group_ifrs_2024_de.pdf" \
  "https://a1.com/investor-relations/results-center/annual-financial-reports/" \
  "Download 'Jahresfinanzbericht 2024' (DE)"

# Semperit AG
download at "semperit_ifrs_2024_en.pdf" \
  "https://www.semperitgroup.com/fileadmin/user_upload/MediaLibrary/SemperitGroup/Investor_relations/Annual_reports_EN/2024-Annual_Report.pdf"
download at "semperit_ifrs_2024_de.pdf" \
  "https://www.semperitgroup.com/fileadmin/user_upload/MediaLibrary/SemperitGroup/Investor_relations/Annual_reports_DE/2024-Geschaeftsbericht.pdf"

# PORR AG
download at "porr_ifrs_2024_en.pdf" \
  "https://report.porr-group.com/PORR_Geschaeftsbericht_2024_en_sec.pdf"
download at "porr_ifrs_2024_de.pdf" \
  "https://report.porr-group.com/PORR_Jahresfinanzbericht_2024_de_sec.pdf"

# Rosenbauer International
download at "rosenbauer_ifrs_2024_en.pdf" \
  "https://bericht.rosenbauer.com/2024/wp-content/uploads/RB_Annual_Report_2024.pdf"
manual_note at "rosenbauer_ifrs_2024_de.pdf" \
  "https://www.rosenbauer.com/en/at/rosenbauer-group/investor-relations/financial-reports/financial-reports-2024" \
  "Download 'Jahresfinanzbericht 2024' (DE)"

# SBO (Schoeller-Bleckmann)
download at "sbo_ifrs_2024_en.pdf" \
  "https://a.storyblok.com/f/321294/x/0627e381b9/ar-24_en_final_links.pdf"
manual_note at "sbo_ifrs_2024_de.pdf" \
  "https://www.sbo.at/en/investor-relations/reports-publications" \
  "Download 'Geschäftsbericht 2024' (DE)"

# AT&S (FY ends Mar 31)
download at "ats_ifrs_2024_en.pdf" \
  "https://ats.net/en/download/annual-report-2023-24/?wpdmdl=34692"
download at "ats_ifrs_2024_de.pdf" \
  "https://ats.net/download/geschaeftsbericht-2023-24/?wpdmdl=34691"

# voestalpine (FY ends Mar 31)
download at "voestalpine_ifrs_2025_en.pdf" \
  "https://www.voestalpine.com/group/static/sites/group/.downloads/en/publications-2024-25/2024-25-annual-report.pdf"
download at "voestalpine_ifrs_2025_de.pdf" \
  "https://www.voestalpine.com/group/static/sites/group/.downloads/de/publikationen-2024-25/2024-25-geschaeftsbericht.pdf"

# Kontron AG
manual_note at "kontron_ifrs_2024_en.pdf" \
  "https://www.kontron.com/en/group/investors/financial-reports" \
  "Download 'Annual Report 2024' (EN)"
manual_note at "kontron_ifrs_2024_de.pdf" \
  "https://www.kontron.com/en/group/investors/financial-reports" \
  "Download 'Geschäftsbericht 2024' (DE)"

# Addiko Bank
download at "addiko_ifrs_2024_en.pdf" \
  "https://www.addiko.com/static/uploads/Addiko-Group-Consolidated-Financial-Report-2024-EN-1.pdf"
download at "addiko_ifrs_2024_de.pdf" \
  "https://www.addiko.com/static/uploads/Addiko-Group-Consolidated-Financial-Report-2024-DE-1.pdf"

# BKS Bank
download at "bks_bank_ifrs_2024_en.pdf" \
  "https://www.bks.at/mbxs8qn54zwj/4Ihn8kd3tfVamMm45Nmxt3/790d7b5b98394a8164fa1ae667652188/Annual_Report__2024.pdf"
download at "bks_bank_ifrs_2024_de.pdf" \
  "https://www.bks.at/mbxs8qn54zwj/xmBVRjfxHq0AiUfnUiw7O/c950460c6e9bc74e6809bcf305131244/Jahresfinanzbericht_2024.pdf"

# Polytec Holding
manual_note at "polytec_ifrs_2024_en.pdf" \
  "https://www.polytec-group.com/en/investor-relations/publications" \
  "Download 'Annual Report 2024' (EN)"
manual_note at "polytec_ifrs_2024_de.pdf" \
  "https://www.polytec-group.com/en/investor-relations/publications" \
  "Download 'Geschäftsbericht 2024' (DE)"

echo ""

# ─────────────────────────────────────────────────────────────
# FRENCH (FR) — 29 companies × 2 languages = 58 PDFs
# ─────────────────────────────────────────────────────────────
echo "── FR (French) ──"

# BNP Paribas
manual_note fr "bnp_paribas_ifrs_2024_en.pdf" \
  "https://invest.bnpparibas/en/results-center/annual-reports" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "bnp_paribas_ifrs_2024_fr.pdf" \
  "https://invest.bnpparibas/en/results-center/annual-reports" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# AXA
manual_note fr "axa_ifrs_2024_en.pdf" \
  "https://www.axa.com/en/investor/annual-reports" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "axa_ifrs_2024_fr.pdf" \
  "https://www.axa.com/en/investor/annual-reports" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Eramet
manual_note fr "eramet_ifrs_2024_en.pdf" \
  "https://www.eramet.com/en/investors/publications-and-events/regulated-information" \
  "Download 'URD 2024' or 'Annual Report 2024' (EN)"
manual_note fr "eramet_ifrs_2024_fr.pdf" \
  "https://www.eramet.com/en/investors/publications-and-events/regulated-information" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# TotalEnergies
manual_note fr "totalenergies_ifrs_2024_en.pdf" \
  "https://totalenergies.com/investors/publications-and-regulated-information/regulated-information/annual-financial-reports" \
  "Download 'Universal Registration Document 2024' (EN) or 20-F"
manual_note fr "totalenergies_ifrs_2024_fr.pdf" \
  "https://totalenergies.com/investors/publications-and-regulated-information/regulated-information/annual-financial-reports" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Carrefour
manual_note fr "carrefour_ifrs_2024_en.pdf" \
  "https://www.carrefour.com/en/finance/annual-reports" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "carrefour_ifrs_2024_fr.pdf" \
  "https://www.carrefour.com/en/finance/annual-reports" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Dassault Systèmes
manual_note fr "dassault_systemes_ifrs_2024_en.pdf" \
  "https://investor.3ds.com/financial-information/annual-reports" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "dassault_systemes_ifrs_2024_fr.pdf" \
  "https://investor.3ds.com/financial-information/annual-reports" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Orange
manual_note fr "orange_ifrs_2024_en.pdf" \
  "https://www.orange.com/en/finance/regulated-information" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "orange_ifrs_2024_fr.pdf" \
  "https://www.orange.com/en/finance/regulated-information" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Schneider Electric
manual_note fr "schneider_electric_ifrs_2024_en.pdf" \
  "https://www.se.com/ww/en/about-us/investor-relations/regulated-information.jsp" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "schneider_electric_ifrs_2024_fr.pdf" \
  "https://www.se.com/ww/en/about-us/investor-relations/regulated-information.jsp" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Sanofi
manual_note fr "sanofi_ifrs_2024_en.pdf" \
  "https://www.sanofi.com/en/investors/reports-and-publications" \
  "Download '20-F 2024' or 'Universal Registration Document 2024' (EN)"
manual_note fr "sanofi_ifrs_2024_fr.pdf" \
  "https://www.sanofi.com/en/investors/reports-and-publications" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# L'Oréal
manual_note fr "loreal_ifrs_2024_en.pdf" \
  "https://www.loreal-finance.com/en/annual-report/" \
  "Download 'Universal Registration Document 2024' (EN) — consolidated FS section"
manual_note fr "loreal_ifrs_2024_fr.pdf" \
  "https://www.loreal-finance.com/fr/rapport-annuel/" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Air Liquide
manual_note fr "air_liquide_ifrs_2024_en.pdf" \
  "https://www.airliquide.com/investors/publications" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "air_liquide_ifrs_2024_fr.pdf" \
  "https://www.airliquide.com/investisseurs/publications" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Vinci
manual_note fr "vinci_ifrs_2024_en.pdf" \
  "https://www.vinci.com/vinci.nsf/en/finance-regulated-information/pages/index.htm" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "vinci_ifrs_2024_fr.pdf" \
  "https://www.vinci.com/vinci.nsf/fr/finance-information-reglementee/pages/index.htm" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Renault
manual_note fr "renault_ifrs_2024_en.pdf" \
  "https://www.renaultgroup.com/en/finance/financial-information/regulated-documents/" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "renault_ifrs_2024_fr.pdf" \
  "https://www.renaultgroup.com/finance/information-financiere/documents-reglementes/" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Engie
manual_note fr "engie_ifrs_2024_en.pdf" \
  "https://www.engie.com/en/investors/regulated-information" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "engie_ifrs_2024_fr.pdf" \
  "https://www.engie.com/investisseurs/information-reglementee" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Veolia
manual_note fr "veolia_ifrs_2024_en.pdf" \
  "https://www.veolia.com/en/finance/regulated-information" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "veolia_ifrs_2024_fr.pdf" \
  "https://www.veolia.com/fr/finance/information-reglementee" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Saint-Gobain
manual_note fr "saint_gobain_ifrs_2024_en.pdf" \
  "https://www.saint-gobain.com/en/finance/publications-and-events/annual-reports" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "saint_gobain_ifrs_2024_fr.pdf" \
  "https://www.saint-gobain.com/fr/finance/publications-et-evenements/rapports-annuels" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Pernod Ricard
manual_note fr "pernod_ricard_ifrs_2024_en.pdf" \
  "https://www.pernod-ricard.com/en/investors/regulated-information" \
  "Download 'Universal Registration Document FY2024' (EN) — June year-end"
manual_note fr "pernod_ricard_ifrs_2024_fr.pdf" \
  "https://www.pernod-ricard.com/fr/investisseurs/information-reglementee" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Bouygues
manual_note fr "bouygues_ifrs_2024_en.pdf" \
  "https://www.bouygues.com/en/finance/regulated-information/" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "bouygues_ifrs_2024_fr.pdf" \
  "https://www.bouygues.com/finance/information-reglementee/" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Thales
manual_note fr "thales_ifrs_2024_en.pdf" \
  "https://www.thalesgroup.com/en/investor/regulated-information" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "thales_ifrs_2024_fr.pdf" \
  "https://www.thalesgroup.com/fr/investisseur/information-reglementee" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Société Générale
manual_note fr "socgen_ifrs_2024_en.pdf" \
  "https://investors.societegenerale.com/en/financial-and-regulated-information/financial-reports" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "socgen_ifrs_2024_fr.pdf" \
  "https://investisseurs.societegenerale.com/fr/informations-financieres-et-reglementees/rapports-financiers" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Crédit Agricole
manual_note fr "credit_agricole_ifrs_2024_en.pdf" \
  "https://www.credit-agricole-sa.fr/en/finance/financial-reporting" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "credit_agricole_ifrs_2024_fr.pdf" \
  "https://www.credit-agricole-sa.fr/finance/information-financiere" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Michelin
manual_note fr "michelin_ifrs_2024_en.pdf" \
  "https://www.michelin.com/en/finance/regulated-information/" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "michelin_ifrs_2024_fr.pdf" \
  "https://www.michelin.com/finance/information-reglementee/" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# --- FR mid-caps ---

# Eurazeo
manual_note fr "eurazeo_ifrs_2024_en.pdf" \
  "https://www.eurazeo.com/en/investors" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "eurazeo_ifrs_2024_fr.pdf" \
  "https://www.eurazeo.com/en/investors" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Ipsen
manual_note fr "ipsen_ifrs_2024_en.pdf" \
  "https://www.ipsen.com/investors/" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "ipsen_ifrs_2024_fr.pdf" \
  "https://www.ipsen.com/investors/" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Edenred
manual_note fr "edenred_ifrs_2024_en.pdf" \
  "https://www.edenred.com/en/investors" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "edenred_ifrs_2024_fr.pdf" \
  "https://www.edenred.com/en/investors" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Bureau Veritas
manual_note fr "bureau_veritas_ifrs_2024_en.pdf" \
  "https://group.bureauveritas.com/investors" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "bureau_veritas_ifrs_2024_fr.pdf" \
  "https://group.bureauveritas.com/investors" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Soitec
manual_note fr "soitec_ifrs_2024_en.pdf" \
  "https://investors.soitec.com/en" \
  "Download 'Universal Registration Document FY2024' (EN) — March year-end"
manual_note fr "soitec_ifrs_2024_fr.pdf" \
  "https://investors.soitec.com/en" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Virbac
manual_note fr "virbac_ifrs_2024_en.pdf" \
  "https://www.virbac.com/investors" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "virbac_ifrs_2024_fr.pdf" \
  "https://www.virbac.com/investors" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Rémy Cointreau
manual_note fr "remy_cointreau_ifrs_2024_en.pdf" \
  "https://www.remy-cointreau.com/en/investors/" \
  "Download 'Universal Registration Document FY2024' (EN) — March year-end"
manual_note fr "remy_cointreau_ifrs_2024_fr.pdf" \
  "https://www.remy-cointreau.com/en/investors/" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Mersen
manual_note fr "mersen_ifrs_2024_en.pdf" \
  "https://www.mersen.com/investors" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "mersen_ifrs_2024_fr.pdf" \
  "https://www.mersen.com/investors" \
  "Download 'Document d enregistrement universel 2024' (FR)"

# Trigano
manual_note fr "trigano_ifrs_2024_en.pdf" \
  "https://www.trigano.fr/en/investors/" \
  "Download 'Universal Registration Document 2024' (EN)"
manual_note fr "trigano_ifrs_2024_fr.pdf" \
  "https://www.trigano.fr/en/investors/" \
  "Download 'Document d enregistrement universel 2024' (FR)"

echo ""

# ─────────────────────────────────────────────────────────────
# SPANISH (ES) — 24 companies × 2 languages = 48 PDFs
# ─────────────────────────────────────────────────────────────
echo "── ES (Spanish) ──"

# Santander
download es "santander_ifrs_2024_en.pdf" \
  "https://www.santander.com/content/dam/santander-com/en/documentos/informe-financiero-anual/2024/ifa-2024-consolidated-annual-financial-report-en.pdf"
download es "santander_ifrs_2024_es.pdf" \
  "https://www.santander.com/content/dam/santander-com/es/documentos/informe-financiero-anual/2024/ifa-2024-informe-financiero-anual-consolidado-es.pdf"

# MAPFRE
download es "mapfre_ifrs_2024_es.pdf" \
  "https://www.mapfre.com/media/accionistas/2025/informe-anual-consolidado-2024.pdf"
manual_note es "mapfre_ifrs_2024_en.pdf" \
  "https://www.mapfre.com/en/shareholders-investors/" \
  "Download 'Consolidated Annual Report 2024' (EN)"

# Repsol
download es "repsol_ifrs_2024_en.pdf" \
  "https://www.repsol.com/content/dam/repsol-corporate/en_gb/accionistas-e-inversores/informes-anuales/2024/consolidated-financial-statements.pdf"
download es "repsol_ifrs_2024_es.pdf" \
  "https://www.repsol.com/content/dam/repsol-corporate/es/accionistas-e-inversores/informes-anuales/2024/cuentas-anuales-consolidadas.pdf"

# Inditex
download es "inditex_ifrs_2024_en.pdf" \
  "https://www.inditex.com/itxcomweb/api/media/84135f02-0208-4439-b9c0-b13608fbfeb5/Annualaccountsanddirectorsreport2024consolidated.pdf?t=1742203067340"
download es "inditex_ifrs_2024_es.pdf" \
  "https://www.inditex.com/itxcomweb/api/media/d2407831-0359-41b2-ba3e-654383b27ffb/Cuentasanualeseinformedegestion2024consolidado.pdf?t=1742203269059"

# Amadeus IT
download es "amadeus_ifrs_2024_en.pdf" \
  "https://corporate.amadeus.com/documents/en/investors/2024/financial-results/q4-2024/fy2024-consolidated-accounts.pdf"
manual_note es "amadeus_ifrs_2024_es.pdf" \
  "https://corporate.amadeus.com/es/inversores/informacion-financiera" \
  "Download 'Cuentas consolidadas FY2024' (ES)"

# Telefónica
download es "telefonica_ifrs_2024_en.pdf" \
  "https://www.telefonica.com/en/wp-content/uploads/sites/5/2025/02/Consolidated-Annual-Accounts-2024.pdf"
manual_note es "telefonica_ifrs_2024_es.pdf" \
  "https://www.telefonica.com/es/accionistas-inversores/informes-financieros/informe-anual/" \
  "Download 'Cuentas Anuales Consolidadas 2024' (ES)"

# Ferrovial
download es "ferrovial_ifrs_2024_en.pdf" \
  "https://static-iai.ferrovial.com/wp-content/uploads/sites/13/2025/02/28004913/ferrovial-integrated-annual-report-2024-consolidated-financial-statements-2.pdf"
manual_note es "ferrovial_ifrs_2024_es.pdf" \
  "https://informeanualintegrado2024.ferrovial.com/es/centro-de-descargas/" \
  "Download consolidated FS section from Informe Anual Integrado (ES)"

# Grifols
manual_note es "grifols_ifrs_2024_en.pdf" \
  "https://www.grifols.com/en/annual-accounts" \
  "Download 'Annual Accounts 2024' or 20-F from SEC"
manual_note es "grifols_ifrs_2024_es.pdf" \
  "https://www.grifols.com/en/annual-accounts" \
  "Download 'Cuentas Anuales Consolidadas 2024' (ES)"

# Iberdrola
manual_note es "iberdrola_ifrs_2024_en.pdf" \
  "https://www.iberdrola.com/shareholders-investors/annual-reports" \
  "Download 'Consolidated Financial Statements 2024' (EN)"
manual_note es "iberdrola_ifrs_2024_es.pdf" \
  "https://www.iberdrola.com/accionistas-inversores/informes-anuales" \
  "Download 'Cuentas Anuales Consolidadas 2024' (ES)"

# CaixaBank
manual_note es "caixabank_ifrs_2024_en.pdf" \
  "https://www.caixabank.com/en/shareholders-investors/financial-information/annual-reports.html" \
  "Download 'Annual Report 2024' or consolidated FS (EN)"
manual_note es "caixabank_ifrs_2024_es.pdf" \
  "https://www.caixabank.com/es/accionistas-inversores/informacion-financiera/informes-anuales.html" \
  "Download 'Cuentas Anuales Consolidadas 2024' (ES)"

# Naturgy
manual_note es "naturgy_ifrs_2024_en.pdf" \
  "https://www.naturgy.com/en/shareholders_and_investors/financial_information/annual_accounts" \
  "Download 'Consolidated Annual Accounts 2024' (EN)"
manual_note es "naturgy_ifrs_2024_es.pdf" \
  "https://www.naturgy.com/accionistas_e_inversores/informacion_financiera/cuentas_anuales" \
  "Download 'Cuentas Anuales Consolidadas 2024' (ES)"

# ACS
manual_note es "acs_ifrs_2024_en.pdf" \
  "https://www.grupoacs.com/shareholders-investors/financial-information/annual-accounts/" \
  "Download 'Consolidated Annual Accounts 2024' (EN)"
manual_note es "acs_ifrs_2024_es.pdf" \
  "https://www.grupoacs.com/accionistas-inversores/informacion-financiera/cuentas-anuales/" \
  "Download 'Cuentas Anuales Consolidadas 2024' (ES)"

# Cellnex
manual_note es "cellnex_ifrs_2024_en.pdf" \
  "https://www.cellnextelecom.com/en/investors/financial-information/" \
  "Download 'Consolidated Annual Accounts 2024' (EN)"
manual_note es "cellnex_ifrs_2024_es.pdf" \
  "https://www.cellnextelecom.com/inversores/informacion-financiera/" \
  "Download 'Cuentas Anuales Consolidadas 2024' (ES)"

# Acerinox
manual_note es "acerinox_ifrs_2024_en.pdf" \
  "https://www.acerinox.com/en/shareholders-investors/annual-reports/" \
  "Download 'Annual Report 2024' (EN)"
manual_note es "acerinox_ifrs_2024_es.pdf" \
  "https://www.acerinox.com/accionistas-inversores/informes-anuales/" \
  "Download 'Informe Anual 2024' (ES)"

# Aena
manual_note es "aena_ifrs_2024_en.pdf" \
  "https://www.aena.es/en/shareholders-and-investors/financial-information/annual-accounts.html" \
  "Download 'Consolidated Annual Accounts 2024' (EN)"
manual_note es "aena_ifrs_2024_es.pdf" \
  "https://www.aena.es/es/accionistas-e-inversores/informacion-financiera/cuentas-anuales.html" \
  "Download 'Cuentas Anuales Consolidadas 2024' (ES)"

# Banco Sabadell
manual_note es "sabadell_ifrs_2024_en.pdf" \
  "https://www.grupbancsabadell.com/corp/en/shareholders-and-investors/financial-information/annual-reports.html" \
  "Download 'Annual Report 2024' — consolidated FS with notes (EN)"
manual_note es "sabadell_ifrs_2024_es.pdf" \
  "https://www.grupbancsabadell.com/corp/es/accionistas-e-inversores/informacion-financiera/informes-anuales.html" \
  "Download 'Informe Anual 2024' (ES)"

# --- ES mid-caps ---

# Viscofan
manual_note es "viscofan_ifrs_2024_en.pdf" \
  "https://www.viscofan.com/en/shareholders-and-investors/" \
  "Download 'Annual Report 2024' (EN)"
manual_note es "viscofan_ifrs_2024_es.pdf" \
  "https://www.viscofan.com/en/shareholders-and-investors/" \
  "Download 'Informe Anual 2024' (ES)"

# CAF (Construcciones y Auxiliar de Ferrocarriles)
manual_note es "caf_ifrs_2024_en.pdf" \
  "https://www.caf.net/en/accionistas-inversores/informacion-financiera.php" \
  "Download 'Annual Accounts 2024' (EN)"
manual_note es "caf_ifrs_2024_es.pdf" \
  "https://www.caf.net/en/accionistas-inversores/informacion-financiera.php" \
  "Download 'Cuentas Anuales 2024' (ES)"

# Merlin Properties
manual_note es "merlin_properties_ifrs_2024_en.pdf" \
  "https://www.merlinproperties.com/en/shareholders-investors/" \
  "Download 'Annual Report 2024' — IFRS consolidated (EN)"
manual_note es "merlin_properties_ifrs_2024_es.pdf" \
  "https://www.merlinproperties.com/en/shareholders-investors/" \
  "Download 'Informe Anual 2024' (ES)"

# Fluidra
manual_note es "fluidra_ifrs_2024_en.pdf" \
  "https://investors.fluidra.com/en" \
  "Download 'Annual Report 2024' (EN)"
manual_note es "fluidra_ifrs_2024_es.pdf" \
  "https://investors.fluidra.com/en" \
  "Download 'Informe Anual 2024' (ES)"

# Sacyr
manual_note es "sacyr_ifrs_2024_en.pdf" \
  "https://www.sacyr.com/en/web/shareholders-and-investors" \
  "Download 'Annual Accounts 2024' (EN)"
manual_note es "sacyr_ifrs_2024_es.pdf" \
  "https://www.sacyr.com/en/web/shareholders-and-investors" \
  "Download 'Cuentas Anuales 2024' (ES)"

# Redeia (formerly Red Eléctrica)
manual_note es "redeia_ifrs_2024_en.pdf" \
  "https://www.redeia.com/en/shareholders-and-investors" \
  "Download 'Annual Report 2024' (EN)"
manual_note es "redeia_ifrs_2024_es.pdf" \
  "https://www.redeia.com/en/shareholders-and-investors" \
  "Download 'Informe Anual 2024' (ES)"

# Logista
manual_note es "logista_ifrs_2024_en.pdf" \
  "https://www.logista.com/en/shareholders-investors.html" \
  "Download 'Annual Report 2024' (EN)"
manual_note es "logista_ifrs_2024_es.pdf" \
  "https://www.logista.com/en/shareholders-investors.html" \
  "Download 'Informe Anual 2024' (ES)"

# Almirall
manual_note es "almirall_ifrs_2024_en.pdf" \
  "https://www.almirall.com/investors" \
  "Download 'Annual Report 2024' (EN)"
manual_note es "almirall_ifrs_2024_es.pdf" \
  "https://www.almirall.com/investors" \
  "Download 'Informe Anual 2024' (ES)"

echo ""

# ─────────────────────────────────────────────────────────────
# PORTUGUESE (PT) — 20 companies × 2 languages = 40 PDFs
# ─────────────────────────────────────────────────────────────
echo "── PT (Portuguese) ──"

# BCP Millennium
download pt "bcp_ifrs_2024_pt.pdf" \
  "https://ind.millenniumbcp.pt/pt/Institucional/investidores/Documents/RelatorioContas/2024/RABCP2024Vol1PT.pdf"
manual_note pt "bcp_ifrs_2024_en.pdf" \
  "https://ind.millenniumbcp.pt/en/Institucional/investidores/Pages/RelatorioContas.aspx" \
  "Download 'Annual Report 2024' (EN)"

# Fidelidade
download pt "fidelidade_ifrs_2024_pt.pdf" \
  "https://www.fidelidade.pt/PT/a-fidelidade/QuemSomos/QuemSomos/Documents/24-06-2025/FIDELIDADE_RE_2024_v2.pdf"
download pt "fidelidade_ifrs_2023_en.pdf" \
  "https://www.fidelidade.pt/PT/a-fidelidade/QuemSomos/QuemSomos/Documents/27-05-2024/Annual_Report_Fidelidade%202023_EN.pdf"

# Galp Energia
manual_note pt "galp_ifrs_2024_en.pdf" \
  "https://www.galp.com/corp/en/investors/reports-and-presentations/reports-and-results" \
  "Download 'Annual Integrated Report 2024' (EN)"
manual_note pt "galp_ifrs_2024_pt.pdf" \
  "https://www.galp.com/corp/en/investors/reports-and-presentations/reports-and-results" \
  "Download 'Relatório Integrado Anual 2024' (PT)"

# Jerónimo Martins
manual_note pt "jeronimo_martins_ifrs_2024_en.pdf" \
  "https://www.jeronimomartins.com/en/investors/presentations-and-reports/" \
  "Download 'Annual Report 2024' PDF (EN) — ensure full FS with notes"
manual_note pt "jeronimo_martins_ifrs_2024_pt.pdf" \
  "https://www.jeronimomartins.com/en/investors/presentations-and-reports/" \
  "Download 'Relatório e Contas 2024' (PT)"

# NOS SGPS
manual_note pt "nos_ifrs_2024_en.pdf" \
  "https://www.nos.pt/en/institutional/investors/results-and-presentations" \
  "Download 'Annual Report 2024' or ESEF package (EN)"
manual_note pt "nos_ifrs_2024_pt.pdf" \
  "https://www.nos.pt/en/institutional/investors/results-and-presentations" \
  "Download 'Relatório e Contas 2024' (PT)"

# Sonae
manual_note pt "sonae_ifrs_2024_en.pdf" \
  "https://www.sonae.pt/en/investors/reports-and-presentations/" \
  "Download 'Annual Report 2024' (EN)"
manual_note pt "sonae_ifrs_2024_pt.pdf" \
  "https://www.sonae.pt/pt/investidores/relatorios-e-apresentacoes/" \
  "Download 'Relatório e Contas 2024' (PT)"

# CTT - Correios de Portugal
manual_note pt "ctt_ifrs_2024_en.pdf" \
  "https://www.ctt.pt/grupo-ctt/investidores/informacao-financeira/relatorios-e-contas" \
  "Download 'Annual Report 2024' (EN)"
manual_note pt "ctt_ifrs_2024_pt.pdf" \
  "https://www.ctt.pt/grupo-ctt/investidores/informacao-financeira/relatorios-e-contas" \
  "Download 'Relatório e Contas 2024' (PT)"

# Navigator Company
manual_note pt "navigator_ifrs_2024_en.pdf" \
  "https://en.thenavigatorcompany.com/Investors/Annual-Reports" \
  "Download 'Annual Report 2024' (EN)"
manual_note pt "navigator_ifrs_2024_pt.pdf" \
  "https://www.thenavigatorcompany.com/Investidores/Relatorios-Anuais" \
  "Download 'Relatório e Contas 2024' (PT)"

# Corticeira Amorim
manual_note pt "corticeira_amorim_ifrs_2024_en.pdf" \
  "https://www.amorim.com/en/investors/reports-and-presentations/" \
  "Download 'Annual Report 2024' (EN)"
manual_note pt "corticeira_amorim_ifrs_2024_pt.pdf" \
  "https://www.amorim.com/investidores/relatorios-e-apresentacoes/" \
  "Download 'Relatório e Contas 2024' (PT)"

# Mota-Engil
manual_note pt "mota_engil_ifrs_2024_en.pdf" \
  "https://www.mota-engil.com/en/investors/financial-information/" \
  "Download 'Annual Report 2024' (EN)"
manual_note pt "mota_engil_ifrs_2024_pt.pdf" \
  "https://www.mota-engil.com/investidores/informacao-financeira/" \
  "Download 'Relatório e Contas 2024' (PT)"

# EDP Renováveis
manual_note pt "edp_renovaveis_ifrs_2024_en.pdf" \
  "https://www.edpr.com/en/investors/reports-results-and-presentations" \
  "Download 'Annual Report 2024' (EN)"
manual_note pt "edp_renovaveis_ifrs_2024_pt.pdf" \
  "https://www.edpr.com/pt-pt/investidores/relatorios-resultados-e-apresentacoes" \
  "Download 'Relatório e Contas 2024' (PT)"

# REN - Redes Energéticas Nacionais
manual_note pt "ren_ifrs_2024_en.pdf" \
  "https://www.ren.pt/en/investors/reports-results-and-presentations" \
  "Download 'Annual Report 2024' (EN)"
manual_note pt "ren_ifrs_2024_pt.pdf" \
  "https://www.ren.pt/pt/investidores/relatorios-resultados-e-apresentacoes" \
  "Download 'Relatório e Contas 2024' (PT)"

# Petrobras (Brazilian but IFRS, PT/EN bilingual)
manual_note pt "petrobras_ifrs_2024_en.pdf" \
  "https://www.investidorpetrobras.com.br/en/results-and-announcements/annual-reports/" \
  "Download '20-F 2024' or 'Annual Report 2024' (EN)"
manual_note pt "petrobras_ifrs_2024_pt.pdf" \
  "https://www.investidorpetrobras.com.br/resultados-e-comunicados/relatorios-anuais/" \
  "Download 'Relatório Anual 2024' (PT)"

# Vale (Brazilian, IFRS)
manual_note pt "vale_ifrs_2024_en.pdf" \
  "https://www.vale.com/investors/financial-data-reports/annual-reports-and-sustainability" \
  "Download '20-F 2024' or 'Annual Report 2024' (EN)"
manual_note pt "vale_ifrs_2024_pt.pdf" \
  "https://www.vale.com/investidores/dados-financeiros-relatorios/relatorios-anuais-sustentabilidade" \
  "Download 'Relatório Anual 2024' (PT)"

# Ambev (Brazilian, IFRS)
manual_note pt "ambev_ifrs_2024_en.pdf" \
  "https://ri.ambev.com.br/en/financial-information/annual-reports/" \
  "Download 'Annual Report 2024' or '20-F' (EN)"
manual_note pt "ambev_ifrs_2024_pt.pdf" \
  "https://ri.ambev.com.br/informacoes-financeiras/relatorios-anuais/" \
  "Download 'Relatório Anual 2024' (PT)"

# --- PT mid-caps ---

# Semapa
manual_note pt "semapa_ifrs_2024_en.pdf" \
  "https://www.semapa.pt/en/investors" \
  "Download 'Annual Report 2024' (EN)"
manual_note pt "semapa_ifrs_2024_pt.pdf" \
  "https://www.semapa.pt/en/investors" \
  "Download 'Relatório e Contas 2024' (PT)"

# Altri
manual_note pt "altri_ifrs_2024_en.pdf" \
  "https://www.altri.pt/en/investors" \
  "Download 'Annual Report 2024' (EN)"
manual_note pt "altri_ifrs_2024_pt.pdf" \
  "https://www.altri.pt/en/investors" \
  "Download 'Relatório e Contas 2024' (PT)"

# Greenvolt
manual_note pt "greenvolt_ifrs_2024_en.pdf" \
  "https://www.greenvolt.com/en/investors/" \
  "Download 'Annual Report 2024' (EN)"
manual_note pt "greenvolt_ifrs_2024_pt.pdf" \
  "https://www.greenvolt.com/en/investors/" \
  "Download 'Relatório e Contas 2024' (PT)"

# Gerdau (Brazilian, steel)
manual_note pt "gerdau_ifrs_2024_en.pdf" \
  "https://ri.gerdau.com/en/" \
  "Download '20-F 2024' or 'Annual Report 2024' (EN)"
manual_note pt "gerdau_ifrs_2024_pt.pdf" \
  "https://ri.gerdau.com/en/" \
  "Download 'Relatório Anual 2024' (PT)"

# Embraer (Brazilian, aerospace)
manual_note pt "embraer_ifrs_2024_en.pdf" \
  "https://ri.embraer.com.br/en/" \
  "Download '20-F 2024' or 'Annual Report 2024' (EN)"
manual_note pt "embraer_ifrs_2024_pt.pdf" \
  "https://ri.embraer.com.br/en/" \
  "Download 'Relatório Anual 2024' (PT)"

# Suzano (Brazilian, pulp & paper)
manual_note pt "suzano_ifrs_2024_en.pdf" \
  "https://ir.suzano.com.br/en/" \
  "Download '20-F 2024' or 'Annual Report 2024' (EN)"
manual_note pt "suzano_ifrs_2024_pt.pdf" \
  "https://ir.suzano.com.br/en/" \
  "Download 'Relatório Anual 2024' (PT)"

# CPFL Energia (Brazilian, utility)
manual_note pt "cpfl_energia_ifrs_2024_en.pdf" \
  "https://ri.cpfl.com.br/en/" \
  "Download '20-F 2024' (EN)"
manual_note pt "cpfl_energia_ifrs_2024_pt.pdf" \
  "https://ri.cpfl.com.br/en/" \
  "Download 'Relatório Anual 2024' (PT)"

# --- PT/BR additional ---

# Ibersol (PT, food/hospitality)
manual_note pt "ibersol_ifrs_2024_en.pdf" \
  "https://www.ibersol.pt/en/investors/" \
  "Download 'Annual Report 2024' (EN)"
manual_note pt "ibersol_ifrs_2024_pt.pdf" \
  "https://www.ibersol.pt/en/investors/" \
  "Download 'Relatório e Contas 2024' (PT)"

# Ramada Aços (PT, steel)
manual_note pt "ramada_acos_ifrs_2024_en.pdf" \
  "https://www.ramadaacos.pt/en/investors/" \
  "Download 'Annual Report 2024' (EN)"
manual_note pt "ramada_acos_ifrs_2024_pt.pdf" \
  "https://www.ramadaacos.pt/en/investors/" \
  "Download 'Relatório e Contas 2024' (PT)"

# Itaú Unibanco (BR, banking)
manual_note pt "itau_unibanco_ifrs_2024_en.pdf" \
  "https://www.itau.com.br/relacoes-com-investidores/en/" \
  "Download '20-F 2024' (EN)"
manual_note pt "itau_unibanco_ifrs_2024_pt.pdf" \
  "https://www.itau.com.br/relacoes-com-investidores/en/" \
  "Download 'Demonstrações Financeiras Consolidadas 2024' (PT)"

# Banco Bradesco (BR, banking)
manual_note pt "bradesco_ifrs_2024_en.pdf" \
  "https://www.bradescori.com.br/en/" \
  "Download '20-F 2024' (EN)"
manual_note pt "bradesco_ifrs_2024_pt.pdf" \
  "https://www.bradescori.com.br/en/" \
  "Download 'Demonstrações Financeiras Consolidadas 2024' (PT)"

# JBS (BR, food/agribusiness)
manual_note pt "jbs_ifrs_2024_en.pdf" \
  "https://ri.jbs.com.br/en/" \
  "Download '20-F 2024' (EN)"
manual_note pt "jbs_ifrs_2024_pt.pdf" \
  "https://ri.jbs.com.br/en/" \
  "Download 'Demonstrações Financeiras Consolidadas 2024' (PT)"

# BRF / Brasil Foods (BR, food)
manual_note pt "brf_ifrs_2024_en.pdf" \
  "https://ri.brf-global.com/en/" \
  "Download '20-F 2024' (EN)"
manual_note pt "brf_ifrs_2024_pt.pdf" \
  "https://ri.brf-global.com/en/" \
  "Download 'Demonstrações Financeiras Consolidadas 2024' (PT)"

# CSN (BR, steel/mining)
manual_note pt "csn_ifrs_2024_en.pdf" \
  "https://ri.csn.com.br/en/" \
  "Download '20-F 2024' (EN)"
manual_note pt "csn_ifrs_2024_pt.pdf" \
  "https://ri.csn.com.br/en/" \
  "Download 'Demonstrações Financeiras Consolidadas 2024' (PT)"

# TIM Brasil (BR, telecom)
manual_note pt "tim_brasil_ifrs_2024_en.pdf" \
  "https://ri.tim.com.br/en/" \
  "Download '20-F 2024' (EN)"
manual_note pt "tim_brasil_ifrs_2024_pt.pdf" \
  "https://ri.tim.com.br/en/" \
  "Download 'Demonstrações Financeiras Consolidadas 2024' (PT)"

# Azul (BR, airlines)
manual_note pt "azul_ifrs_2024_en.pdf" \
  "https://ri.voeazul.com.br/en/" \
  "Download '20-F 2024' (EN)"
manual_note pt "azul_ifrs_2024_pt.pdf" \
  "https://ri.voeazul.com.br/en/" \
  "Download 'Demonstrações Financeiras Consolidadas 2024' (PT)"

echo ""

# ─────────────────────────────────────────────────────────────
# ITALIAN (IT) — 27 companies × 2 languages = 54 PDFs
# ─────────────────────────────────────────────────────────────
echo "── IT (Italian) ──"

# UniCredit
manual_note it "unicredit_ifrs_2024_en.pdf" \
  "https://financialreports.unicredit.eu/" \
  "Download 'Consolidated Financial Statements 2024' (EN)"
manual_note it "unicredit_ifrs_2024_it.pdf" \
  "https://financialreports.unicredit.eu/" \
  "Download 'Bilancio Consolidato 2024' (IT)"

# Generali
download it "generali_ifrs_2024_en.pdf" \
  "https://www.generali.com/doc/jcr:259c5d6e-46f7-4a43-9512-58e5dcbd2a56/Annual%20Integrated%20Report%20and%20Consolidated%20Financial%20Statements%202024_Generali%20Group_final_interactive.pdf/lang:en/Annual_Integrated_Report_and_Consolidated_Financial_Statements_2024_Generali_Group_final_interactive.pdf"
download it "generali_ifrs_2024_it.pdf" \
  "https://www.generali.com/doc/jcr:259c5d6e-46f7-4a43-9512-58e5dcbd2a56/Relazione%20Annuale%20Integrata%20e%20Bilancio%20Consolidato%202024_Gruppo%20Generali_finale_interattiva.pdf/lang:it/Relazione_Annuale_Integrata_e_Bilancio_Consolidato_2024_Gruppo_Generali_finale_interattiva.pdf"

# ENI
download it "eni_ifrs_2024_en.pdf" \
  "https://www.eni.com/content/dam/enicom/documents/eng/reports/2024/ar-2024/Annual-Report-On-Form-20-F-2024.pdf"
manual_note it "eni_ifrs_2024_it.pdf" \
  "https://www.eni.com/it-IT/investors/bilanci-relazioni.html" \
  "Download 'Relazione Finanziaria Annuale 2024' (IT)"

# STMicroelectronics (20-F, Netherlands HQ but IT language via Italy listing)
manual_note it "stmicroelectronics_ifrs_2024_en.pdf" \
  "https://investors.st.com/financial-information/sec-filings" \
  "Download '20-F 2024' from SEC or ST IR page"
# Note: STMicro reports in EN/FR, not IT — skip IT version
manual_note it "stmicroelectronics_ifrs_2024_fr.pdf" \
  "https://investors.st.com/financial-information/annual-reports" \
  "STMicro publishes in EN and FR (Netherlands HQ). Download FR version."

# TIM (Telecom Italia)
manual_note it "tim_ifrs_2024_en.pdf" \
  "https://www.gruppotim.it/en/investors/reports-presentations/financial-reports/2024.html" \
  "Download 'Relazione Finanziaria Annuale 2024' (EN)"
manual_note it "tim_ifrs_2024_it.pdf" \
  "https://www.gruppotim.it/en/investors/reports-presentations/financial-reports/2024.html" \
  "Download 'Relazione Finanziaria Annuale 2024' (IT)"

# Leonardo
manual_note it "leonardo_ifrs_2024_en.pdf" \
  "https://www.leonardo.com/en/investors/results-and-reports" \
  "Download 'Integrated Annual Report 2024' (EN) — 8.8MB PDF"
download it "leonardo_ifrs_2024_it.pdf" \
  "https://www.leonardo.com/documents/15646808/28608810/Bilancio+Integrato+2024.pdf?t=1741973485310"

# Recordati
manual_note it "recordati_ifrs_2024_en.pdf" \
  "https://recordati.com/investors-presentations-and-reports/" \
  "Download 'Annual Report 2024' (EN)"
manual_note it "recordati_ifrs_2024_it.pdf" \
  "https://recordati.com/it/investors-presentations-and-reports-it/" \
  "Download 'Bilancio Consolidato Integrato 2024' (IT)"

# Enel
manual_note it "enel_ifrs_2024_en.pdf" \
  "https://www.enel.com/investors/financials/annual-report" \
  "Download 'Annual Report 2024' — consolidated FS with notes (EN)"
manual_note it "enel_ifrs_2024_it.pdf" \
  "https://www.enel.com/it/investitori/dati-finanziari/bilancio-annuale" \
  "Download 'Relazione Finanziaria Annuale 2024' (IT)"

# Ferrari
manual_note it "ferrari_ifrs_2024_en.pdf" \
  "https://www.ferrari.com/en-EN/corporate/governance-and-reports" \
  "Download '20-F 2024' or 'Annual Report 2024' (EN)"
manual_note it "ferrari_ifrs_2024_it.pdf" \
  "https://www.ferrari.com/it-IT/corporate/governance-and-reports" \
  "Download 'Relazione Finanziaria Annuale 2024' (IT)"

# Intesa Sanpaolo
manual_note it "intesa_sanpaolo_ifrs_2024_en.pdf" \
  "https://group.intesasanpaolo.com/en/investors/financial-reports" \
  "Download 'Annual Report 2024' — consolidated FS with notes (EN)"
manual_note it "intesa_sanpaolo_ifrs_2024_it.pdf" \
  "https://group.intesasanpaolo.com/it/investitori/bilanci-e-relazioni" \
  "Download 'Relazione e Bilancio 2024' (IT)"

# Pirelli
manual_note it "pirelli_ifrs_2024_en.pdf" \
  "https://corporate.pirelli.com/corporate/en-ww/investors/annual-reports" \
  "Download 'Annual Report 2024' (EN)"
manual_note it "pirelli_ifrs_2024_it.pdf" \
  "https://corporate.pirelli.com/corporate/it-it/investors/annual-reports" \
  "Download 'Relazione Annuale 2024' (IT)"

# Prysmian
manual_note it "prysmian_ifrs_2024_en.pdf" \
  "https://www.prysmian.com/en/investors/results-and-reports" \
  "Download 'Annual Report 2024' (EN)"
manual_note it "prysmian_ifrs_2024_it.pdf" \
  "https://www.prysmian.com/it/investitori/risultati-e-bilanci" \
  "Download 'Relazione Finanziaria Annuale 2024' (IT)"

# Moncler
manual_note it "moncler_ifrs_2024_en.pdf" \
  "https://www.monclergroup.com/en/investors/results-reports-and-presentations" \
  "Download 'Annual Report 2024' (EN)"
manual_note it "moncler_ifrs_2024_it.pdf" \
  "https://www.monclergroup.com/it/investitori/risultati-bilanci-e-presentazioni" \
  "Download 'Relazione Finanziaria Annuale 2024' (IT)"

# Campari
manual_note it "campari_ifrs_2024_en.pdf" \
  "https://www.camparigroup.com/en/page/investors-annual-reports" \
  "Download 'Annual Report 2024' (EN)"
manual_note it "campari_ifrs_2024_it.pdf" \
  "https://www.camparigroup.com/it/pagina/investitori-bilanci-annuali" \
  "Download 'Relazione Finanziaria Annuale 2024' (IT)"

# A2A
manual_note it "a2a_ifrs_2024_en.pdf" \
  "https://www.a2a.eu/en/investors/results-and-reports" \
  "Download 'Annual Report 2024' (EN)"
manual_note it "a2a_ifrs_2024_it.pdf" \
  "https://www.a2a.eu/it/investitori/risultati-e-bilanci" \
  "Download 'Relazione Finanziaria Annuale 2024' (IT)"

# Hera
manual_note it "hera_ifrs_2024_en.pdf" \
  "https://eng.gruppohera.it/investors/financial-reports" \
  "Download 'Annual Report 2024' (EN)"
manual_note it "hera_ifrs_2024_it.pdf" \
  "https://www.gruppohera.it/investitori/bilanci-e-relazioni" \
  "Download 'Relazione Finanziaria Annuale 2024' (IT)"

# Mediobanca
manual_note it "mediobanca_ifrs_2024_en.pdf" \
  "https://www.mediobanca.com/en/investor-relations/financial-documents.html" \
  "Download 'Annual Report 2024' (EN) — June year-end"
manual_note it "mediobanca_ifrs_2024_it.pdf" \
  "https://www.mediobanca.com/it/investor-relations/documenti-finanziari.html" \
  "Download 'Relazione e Bilancio 2024' (IT)"

# --- IT mid-caps ---

# Buzzi
manual_note it "buzzi_ifrs_2024_en.pdf" \
  "https://www.buzzi.com/en/investors" \
  "Download 'Annual Report 2024' (EN)"
manual_note it "buzzi_ifrs_2024_it.pdf" \
  "https://www.buzzi.com/en/investors" \
  "Download 'Relazione Finanziaria Annuale 2024' (IT)"

# BPER Banca
manual_note it "bper_banca_ifrs_2024_en.pdf" \
  "https://www.bfranca.it/en/investor-relations" \
  "Download 'Annual Report 2024' (EN)"
manual_note it "bper_banca_ifrs_2024_it.pdf" \
  "https://www.bfranca.it/en/investor-relations" \
  "Download 'Relazione e Bilancio 2024' (IT)"

# Interpump Group
manual_note it "interpump_ifrs_2024_en.pdf" \
  "https://www.interpumpgroup.it/en/investor-relations/" \
  "Download 'Annual Report 2024' (EN)"
manual_note it "interpump_ifrs_2024_it.pdf" \
  "https://www.interpumpgroup.it/en/investor-relations/" \
  "Download 'Relazione Finanziaria Annuale 2024' (IT)"

# De'Longhi
manual_note it "delonghi_ifrs_2024_en.pdf" \
  "https://www.delonghigroup.com/en/investor-relations" \
  "Download 'Annual Report 2024' (EN)"
manual_note it "delonghi_ifrs_2024_it.pdf" \
  "https://www.delonghigroup.com/en/investor-relations" \
  "Download 'Relazione Finanziaria Annuale 2024' (IT)"

# Reply
manual_note it "reply_ifrs_2024_en.pdf" \
  "https://www.reply.com/en/investors" \
  "Download 'Annual Report 2024' (EN)"
manual_note it "reply_ifrs_2024_it.pdf" \
  "https://www.reply.com/en/investors" \
  "Download 'Relazione Finanziaria Annuale 2024' (IT)"

# Technogym
manual_note it "technogym_ifrs_2024_en.pdf" \
  "https://www.technogym.com/en/investor-relations/" \
  "Download 'Annual Report 2024' (EN)"
manual_note it "technogym_ifrs_2024_it.pdf" \
  "https://www.technogym.com/en/investor-relations/" \
  "Download 'Relazione Finanziaria Annuale 2024' (IT)"

# Iren
manual_note it "iren_ifrs_2024_en.pdf" \
  "https://www.gruppoiren.it/en/investors" \
  "Download 'Annual Report 2024' (EN)"
manual_note it "iren_ifrs_2024_it.pdf" \
  "https://www.gruppoiren.it/en/investors" \
  "Download 'Relazione Finanziaria Annuale 2024' (IT)"

# Carel Industries
manual_note it "carel_ifrs_2024_en.pdf" \
  "https://www.carel.com/investor-relations" \
  "Download 'Annual Report 2024' (EN)"
manual_note it "carel_ifrs_2024_it.pdf" \
  "https://www.carel.com/investor-relations" \
  "Download 'Relazione Finanziaria Annuale 2024' (IT)"

# SOL Group
manual_note it "sol_ifrs_2024_en.pdf" \
  "https://www.solgroup.com/en/investor-relations/" \
  "Download 'Annual Report 2024' (EN)"
manual_note it "sol_ifrs_2024_it.pdf" \
  "https://www.solgroup.com/en/investor-relations/" \
  "Download 'Relazione Finanziaria Annuale 2024' (IT)"

# Banca Ifis
manual_note it "banca_ifis_ifrs_2024_en.pdf" \
  "https://www.bancaifis.it/en/investor-relations/" \
  "Download 'Annual Report 2024' (EN)"
manual_note it "banca_ifis_ifrs_2024_it.pdf" \
  "https://www.bancaifis.it/en/investor-relations/" \
  "Download 'Relazione e Bilancio 2024' (IT)"

echo ""

# ─────────────────────────────────────────────────────────────
# CZECH (CZ) — 10 companies × 2 languages = 20 PDFs
# ─────────────────────────────────────────────────────────────
echo "── CZ (Czech) ──"

# Philip Morris CR
manual_note cz "philip_morris_cr_ifrs_2024_en.pdf" \
  "https://www.pmi.com/markets/czech-republic/en/investor-relations/shareholder-information/" \
  "Download 'Annual Financial Report 2024' unofficial EN PDF"
manual_note cz "philip_morris_cr_ifrs_2024_cz.pdf" \
  "https://www.pmi.com/markets/czech-republic/en/investor-relations/shareholder-information/" \
  "Download 'Výroční finanční zpráva 2024' (CZ)"

# Colt CZ Group
manual_note cz "colt_cz_group_ifrs_2024_en.pdf" \
  "https://www.coltczgroup.com/en/investors-financial-results-and-presentations/" \
  "Download 'Annual Financial Report 2024' (EN)"
manual_note cz "colt_cz_group_ifrs_2024_cz.pdf" \
  "https://www.coltczgroup.com/en/investors-financial-results-and-presentations/" \
  "Download 'Výroční finanční zpráva 2024' (CZ)"

# Kofola CeskoSlovensko
manual_note cz "kofola_ifrs_2024_en.pdf" \
  "https://investor.kofola.cz/en/investor-2/reports-and-presentations/financial-reports" \
  "Download 'Annual Report 2024' (EN)"
manual_note cz "kofola_ifrs_2024_cz.pdf" \
  "https://investor.kofola.cz/en/investor-2/reports-and-presentations/financial-reports" \
  "Download 'Výroční zpráva 2024' (CZ)"

# Czechoslovak Group (CSG)
manual_note cz "csg_ifrs_2024_en.pdf" \
  "https://czechoslovakgroup.com/en/for-investors" \
  "Download 'Annual Report 2024' (EN)"
manual_note cz "csg_ifrs_2024_cz.pdf" \
  "https://czechoslovakgroup.com/en/for-investors" \
  "Download 'Výroční zpráva 2024' (CZ)"

# CSOB (Ceskoslovenska obchodni banka)
manual_note cz "csob_ifrs_2024_en.pdf" \
  "https://www.csob.cz/portal/en/about-csob/investor-relations" \
  "Download 'Annual Report 2024' (EN)"
manual_note cz "csob_ifrs_2024_cz.pdf" \
  "https://www.csob.cz/portal/en/about-csob/investor-relations" \
  "Download 'Výroční zpráva 2024' (CZ)"

# Ceska sporitelna
manual_note cz "ceska_sporitelna_ifrs_2024_en.pdf" \
  "https://www.csas.cz/en/about-us/business-results-of-ceska-sporitelna" \
  "Download 'Annual Report 2024' (EN)"
manual_note cz "ceska_sporitelna_ifrs_2024_cz.pdf" \
  "https://www.csas.cz/en/about-us/business-results-of-ceska-sporitelna" \
  "Download 'Výroční zpráva 2024' (CZ)"

# ORLEN Unipetrol
manual_note cz "orlen_unipetrol_ifrs_2024_en.pdf" \
  "https://www.orlenunipetrol.cz/en/InvestorRelations/" \
  "Download 'Annual Report 2024' (EN)"
manual_note cz "orlen_unipetrol_ifrs_2024_cz.pdf" \
  "https://www.orlenunipetrol.cz/en/InvestorRelations/" \
  "Download 'Výroční zpráva 2024' (CZ)"

# Primoco UAV
manual_note cz "primoco_uav_ifrs_2024_en.pdf" \
  "https://www.uav-stol.com/en/for_investors/" \
  "Download 'Annual Financial Report 2024' (EN)"
manual_note cz "primoco_uav_ifrs_2024_cz.pdf" \
  "https://www.uav-stol.com/en/for_investors/" \
  "Download 'Výroční finanční zpráva 2024' (CZ)"

# CEZ Group (already have EN, add CZ)
manual_note cz "cez_ifrs_2024_cz.pdf" \
  "https://www.cez.cz/cs/pro-investory/vyrocni-zpravy" \
  "Download 'Výroční zpráva 2024' (CZ) — EN version already downloaded"

# Komercni Banka (already have EN, add CZ)
manual_note cz "komercni_banka_ifrs_2024_cz.pdf" \
  "https://www.kb.cz/cs/o-bance/pro-investory" \
  "Download 'Výroční zpráva 2024' (CZ) — EN version already downloaded"

echo ""

# ─────────────────────────────────────────────────────────────
# HUNGARIAN (HU) — 12 companies × 2 languages = 24 PDFs
# ─────────────────────────────────────────────────────────────
echo "── HU (Hungarian) ──"

# Magyar Telekom
manual_note hu "magyar_telekom_ifrs_2024_en.pdf" \
  "https://www.telekom.hu/about_us/investor_relations" \
  "Download 'Annual Report 2024' (EN)"
manual_note hu "magyar_telekom_ifrs_2024_hu.pdf" \
  "https://www.telekom.hu/about_us/investor_relations" \
  "Download 'Éves jelentés 2024' (HU)"

# 4iG
manual_note hu "4ig_ifrs_2024_en.pdf" \
  "https://4ig.hu/en/investors/" \
  "Download 'Annual Report 2024' (EN)"
manual_note hu "4ig_ifrs_2024_hu.pdf" \
  "https://4ig.hu/en/investors/" \
  "Download 'Éves jelentés 2024' (HU)"

# Opus Global
manual_note hu "opus_global_ifrs_2024_en.pdf" \
  "https://opusglobal.hu/en/investors/" \
  "Download 'Annual Report 2024' (EN)"
manual_note hu "opus_global_ifrs_2024_hu.pdf" \
  "https://opusglobal.hu/en/investors/" \
  "Download 'Éves jelentés 2024' (HU)"

# Masterplast
manual_note hu "masterplast_ifrs_2024_en.pdf" \
  "https://masterplast.com/en/investors/" \
  "Download 'Annual Report 2024' (EN)"
manual_note hu "masterplast_ifrs_2024_hu.pdf" \
  "https://masterplast.com/en/investors/" \
  "Download 'Éves jelentés 2024' (HU)"

# ANY Biztonsági Nyomda
manual_note hu "any_nyomda_ifrs_2024_en.pdf" \
  "https://www.any.hu/en/investors" \
  "Download 'Annual Report 2024' (EN)"
manual_note hu "any_nyomda_ifrs_2024_hu.pdf" \
  "https://www.any.hu/en/investors" \
  "Download 'Éves jelentés 2024' (HU)"

# Waberer's International
manual_note hu "waberers_ifrs_2024_en.pdf" \
  "https://www.waberers.com/en/investors" \
  "Download 'Annual Report 2024' (EN)"
manual_note hu "waberers_ifrs_2024_hu.pdf" \
  "https://www.waberers.com/en/investors" \
  "Download 'Éves jelentés 2024' (HU)"

# AutoWallis
manual_note hu "autowallis_ifrs_2024_en.pdf" \
  "https://autowallis.hu/en/investors/" \
  "Download 'Annual Report 2024' (EN)"
manual_note hu "autowallis_ifrs_2024_hu.pdf" \
  "https://autowallis.hu/en/investors/" \
  "Download 'Éves jelentés 2024' (HU)"

# ALTEO Energiaszolgáltató
manual_note hu "alteo_ifrs_2024_en.pdf" \
  "https://alteo.hu/en/investors/" \
  "Download 'Annual Report 2024' (EN)"
manual_note hu "alteo_ifrs_2024_hu.pdf" \
  "https://alteo.hu/en/investors/" \
  "Download 'Éves jelentés 2024' (HU)"

# Duna House
manual_note hu "duna_house_ifrs_2024_en.pdf" \
  "https://dunahouse.com/en/investors/" \
  "Download 'Annual Report 2024' (EN)"
manual_note hu "duna_house_ifrs_2024_hu.pdf" \
  "https://dunahouse.com/en/investors/" \
  "Download 'Éves jelentés 2024' (HU)"

# Appeninn
manual_note hu "appeninn_ifrs_2024_en.pdf" \
  "https://appeninn.hu/en/investors/" \
  "Download 'Annual Report 2024' (EN)"
manual_note hu "appeninn_ifrs_2024_hu.pdf" \
  "https://appeninn.hu/en/investors/" \
  "Download 'Éves jelentés 2024' (HU)"

# MOL (already have EN, add HU)
manual_note hu "mol_ifrs_2024_hu.pdf" \
  "https://molgroup.info/hu/befektetoknek/jelentes-es-kiadvanyok/eves-jelentes" \
  "Download 'Éves jelentés 2024' (HU) — EN version already downloaded"

# OTP Bank (already have EN, add HU)
manual_note hu "otp_bank_ifrs_2024_hu.pdf" \
  "https://www.otpbank.hu/portal/hu/Befektetok/Eves_jelentes" \
  "Download 'Éves jelentés 2024' (HU) — EN version already downloaded"

echo ""

# ─────────────────────────────────────────────────────────────
# POLISH (PL) — 9 companies × 2 languages = 18 PDFs
# ─────────────────────────────────────────────────────────────
echo "── PL (Polish) ──"

# PKO BP
manual_note pl "pko_bp_ifrs_2024_en.pdf" \
  "https://www.pkobp.pl/investor-relations/results-center/financial-data/" \
  "Download 'Consolidated Financial Statements 2024' (EN)"
manual_note pl "pko_bp_ifrs_2024_pl.pdf" \
  "https://www.pkobp.pl/relacje-inwestorskie/centrum-wynikow/dane-finansowe/" \
  "Download 'Skonsolidowane Sprawozdanie Finansowe 2024' (PL)"

# PZU
manual_note pl "pzu_ifrs_2024_en.pdf" \
  "https://www.pzu.pl/en/investor-relations/reports-and-publications" \
  "Download 'Consolidated Financial Statements 2024' (EN)"
manual_note pl "pzu_ifrs_2024_pl.pdf" \
  "https://www.pzu.pl/relacje-inwestorskie/raporty-i-publikacje" \
  "Download 'Skonsolidowane Sprawozdanie Finansowe 2024' (PL)"

# KGHM Polska Miedź
manual_note pl "kghm_ifrs_2024_en.pdf" \
  "https://kghm.com/en/investors/reports-and-publications/periodical-reports" \
  "Download 'Consolidated Financial Statements 2024' (EN)"
manual_note pl "kghm_ifrs_2024_pl.pdf" \
  "https://kghm.com/pl/inwestorzy/raporty-i-publikacje/raporty-okresowe" \
  "Download 'Skonsolidowane Sprawozdanie Finansowe 2024' (PL)"

# PKN Orlen
manual_note pl "pkn_orlen_ifrs_2024_en.pdf" \
  "https://www.orlen.pl/en/investor-relations/reporting-center/annual-reports" \
  "Download 'Consolidated Financial Statements 2024' (EN)"
manual_note pl "pkn_orlen_ifrs_2024_pl.pdf" \
  "https://www.orlen.pl/pl/relacje-inwestorskie/centrum-raportowania/raporty-roczne" \
  "Download 'Skonsolidowane Sprawozdanie Finansowe 2024' (PL)"

# Dino Polska
manual_note pl "dino_polska_ifrs_2024_en.pdf" \
  "https://grupadino.pl/en/investor-relations/#reports" \
  "Download 'Consolidated Financial Statements 2024' (EN)"
manual_note pl "dino_polska_ifrs_2024_pl.pdf" \
  "https://grupadino.pl/relacje-inwestorskie/#raporty" \
  "Download 'Skonsolidowane Sprawozdanie Finansowe 2024' (PL)"

# Asseco Poland
manual_note pl "asseco_poland_ifrs_2024_en.pdf" \
  "https://inwestor.asseco.com/en/reports/" \
  "Download 'Consolidated Financial Statements 2024' (EN)"
manual_note pl "asseco_poland_ifrs_2024_pl.pdf" \
  "https://inwestor.asseco.com/raporty/" \
  "Download 'Skonsolidowane Sprawozdanie Finansowe 2024' (PL)"

# Orange Polska
manual_note pl "orange_polska_ifrs_2024_en.pdf" \
  "https://www.orange-ir.pl/en/results-center" \
  "Download 'Consolidated Financial Statements 2024' (EN)"
manual_note pl "orange_polska_ifrs_2024_pl.pdf" \
  "https://www.orange-ir.pl/centrum-wynikow" \
  "Download 'Skonsolidowane Sprawozdanie Finansowe 2024' (PL)"

# Budimex
manual_note pl "budimex_ifrs_2024_en.pdf" \
  "https://www.budimex.pl/en/investor-relations/reports-and-publications" \
  "Download 'Consolidated Financial Statements 2024' (EN)"
manual_note pl "budimex_ifrs_2024_pl.pdf" \
  "https://www.budimex.pl/relacje-inwestorskie/raporty-i-publikacje" \
  "Download 'Skonsolidowane Sprawozdanie Finansowe 2024' (PL)"

# Bioton (may be XHTML only — check)
manual_note pl "bioton_ifrs_2024_en.pdf" \
  "https://www.bioton.pl/en/investor-relations/reports/" \
  "⚠️ May only publish ESEF/XHTML — verify PDF exists"
manual_note pl "bioton_ifrs_2024_pl.pdf" \
  "https://www.bioton.pl/relacje-inwestorskie/raporty/" \
  "⚠️ May only publish ESEF/XHTML — verify PDF exists"

echo ""

# ─────────────────────────────────────────────────────────────
# NORWEGIAN (NO) — 6 companies × 2 languages = 12 PDFs
# ─────────────────────────────────────────────────────────────
echo "── NO (Norwegian) ──"

# DNB Bank
manual_note no "dnb_ifrs_2024_en.pdf" \
  "https://www.dnb.no/en/about-us/investor-relations/reports.html" \
  "Download 'Annual Report 2024' (EN) — Nordic annual report = full FS with notes"
manual_note no "dnb_ifrs_2024_no.pdf" \
  "https://www.dnb.no/om-oss/investor-relations/rapporter.html" \
  "Download 'Årsrapport 2024' (NO)"

# Gjensidige
manual_note no "gjensidige_ifrs_2024_en.pdf" \
  "https://www.gjensidige.no/group/investor-relations/reports-and-presentations" \
  "Download 'Annual Report 2024' (EN)"
manual_note no "gjensidige_ifrs_2024_no.pdf" \
  "https://www.gjensidige.no/group/investor-relations/reports-and-presentations" \
  "Download 'Årsrapport 2024' (NO)"

# Equinor
manual_note no "equinor_ifrs_2024_en.pdf" \
  "https://www.equinor.com/investors/annual-reports" \
  "Download 'Annual Report 2024' (EN) or 20-F"
manual_note no "equinor_ifrs_2024_no.pdf" \
  "https://www.equinor.com/investors/annual-reports" \
  "Download 'Årsrapport 2024' (NO)"

# Orkla
manual_note no "orkla_ifrs_2024_en.pdf" \
  "https://www.orkla.com/investors/reports-presentations/" \
  "Download 'Annual Report 2024' (EN)"
manual_note no "orkla_ifrs_2024_no.pdf" \
  "https://www.orkla.com/investors/reports-presentations/" \
  "Download 'Årsrapport 2024' (NO)"

# Telenor
manual_note no "telenor_ifrs_2024_en.pdf" \
  "https://www.telenor.com/investors/reports-and-information/annual-report/" \
  "Download 'Annual Report 2024' (EN)"
manual_note no "telenor_ifrs_2024_no.pdf" \
  "https://www.telenor.com/investors/reports-and-information/annual-report/" \
  "Download 'Årsrapport 2024' (NO)"

# Yara
manual_note no "yara_ifrs_2024_en.pdf" \
  "https://www.yara.com/investor-relations/reports-presentations/" \
  "Download 'Annual Report 2024' (EN)"
manual_note no "yara_ifrs_2024_no.pdf" \
  "https://www.yara.com/investor-relations/reports-presentations/" \
  "Download 'Årsrapport 2024' (NO)"

echo ""

# ─────────────────────────────────────────────────────────────
# SWEDISH (SV) — 7 companies × 2 languages = 14 PDFs
# ─────────────────────────────────────────────────────────────
echo "── SV (Swedish) ──"

# SEB
manual_note sv "seb_ifrs_2024_en.pdf" \
  "https://sebgroup.com/investor-relations/reports-and-presentations/annual-reports" \
  "Download 'Annual Report 2024' (EN)"
manual_note sv "seb_ifrs_2024_sv.pdf" \
  "https://sebgroup.com/investor-relations/reports-and-presentations/annual-reports" \
  "Download 'Årsredovisning 2024' (SV)"

# Boliden
manual_note sv "boliden_ifrs_2024_en.pdf" \
  "https://www.boliden.com/investor-relations/reports-and-presentations" \
  "Download 'Annual Report 2024' (EN)"
manual_note sv "boliden_ifrs_2024_sv.pdf" \
  "https://www.boliden.com/investor-relations/reports-and-presentations" \
  "Download 'Årsredovisning 2024' (SV)"

# H&M
manual_note sv "hm_ifrs_2024_en.pdf" \
  "https://hmgroup.com/investors/reports/" \
  "Download 'Annual Report 2024' (EN) — FY ends Nov 30"
manual_note sv "hm_ifrs_2024_sv.pdf" \
  "https://hmgroup.com/investors/reports/" \
  "Download 'Årsredovisning 2024' (SV)"

# Ericsson
manual_note sv "ericsson_ifrs_2024_en.pdf" \
  "https://www.ericsson.com/en/investors/financial-reports" \
  "Download 'Annual Report 2024' (EN) or 20-F"
manual_note sv "ericsson_ifrs_2024_sv.pdf" \
  "https://www.ericsson.com/en/investors/financial-reports" \
  "Download 'Årsredovisning 2024' (SV)"

# Telia
manual_note sv "telia_ifrs_2024_en.pdf" \
  "https://www.teliacompany.com/en/investors/reports-and-presentations" \
  "Download 'Annual Report 2024' (EN)"
manual_note sv "telia_ifrs_2024_sv.pdf" \
  "https://www.teliacompany.com/en/investors/reports-and-presentations" \
  "Download 'Årsredovisning 2024' (SV)"

# Atlas Copco
manual_note sv "atlas_copco_ifrs_2024_en.pdf" \
  "https://www.atlascopcogroup.com/en/investor-relations/financial-publications/annual-reports" \
  "Download 'Annual Report 2024' (EN)"
manual_note sv "atlas_copco_ifrs_2024_sv.pdf" \
  "https://www.atlascopcogroup.com/en/investor-relations/financial-publications/annual-reports" \
  "Download 'Årsredovisning 2024' (SV)"

# AstraZeneca (UK HQ, Swedish listing)
manual_note sv "astrazeneca_ifrs_2024_en.pdf" \
  "https://www.astrazeneca.com/investor-relations/annual-reports.html" \
  "Download 'Annual Report 2024' (EN) or 20-F"
manual_note sv "astrazeneca_ifrs_2024_sv.pdf" \
  "https://www.astrazeneca.com/investor-relations/annual-reports.html" \
  "Download 'Årsredovisning 2024' (SV) — may not exist, AZ is UK-domiciled"

echo ""

# ─────────────────────────────────────────────────────────────
# JAPANESE (JA) — 8 companies × 2 languages = 16 PDFs
# ─────────────────────────────────────────────────────────────
echo "── JA (Japanese) ──"

# SMFG
manual_note ja "smfg_ifrs_2024_en.pdf" \
  "https://www.smfg.co.jp/english/investor/financial/annual.html" \
  "Download '20-F 2025' from SEC or 'Annual Report' from IR page"
manual_note ja "smfg_ifrs_2024_ja.pdf" \
  "https://www.smfg.co.jp/investor/financial/annual.html" \
  "Download '有価証券報告書 2024' (JA) from IR page or EDINET"

# Sompo Holdings (first IFRS filing FY2025 ended Mar 2025)
manual_note ja "sompo_ifrs_2025_en.pdf" \
  "https://www.sompo-hd.com/en/ir/data/annual/" \
  "Download 'Integrated Annual Report' or 'Annual Securities Report' (EN)"
manual_note ja "sompo_ifrs_2025_ja.pdf" \
  "https://www.sompo-hd.com/ir/data/annual/" \
  "Download '有価証券報告書 FY2025' (JA) — first IFRS filing"

# INPEX
manual_note ja "inpex_ifrs_2024_en.pdf" \
  "https://www.inpex.co.jp/english/ir/library/annual.html" \
  "Download 'Annual Securities Report' or 'Annual Report' (EN)"
manual_note ja "inpex_ifrs_2024_ja.pdf" \
  "https://www.inpex.co.jp/ir/library/annual.html" \
  "Download '有価証券報告書 2024' (JA)"

# Fast Retailing (Uniqlo)
manual_note ja "fast_retailing_ifrs_2024_en.pdf" \
  "https://www.fastretailing.com/eng/ir/library/annual.html" \
  "Download 'Annual Securities Report' (EN) — FY ends Aug 31"
manual_note ja "fast_retailing_ifrs_2024_ja.pdf" \
  "https://www.fastretailing.com/jp/ir/library/annual.html" \
  "Download '有価証券報告書 2024' (JA)"

# Sony Group
manual_note ja "sony_ifrs_2025_en.pdf" \
  "https://www.sony.com/en/SonyInfo/IR/library/sec.html" \
  "Download '20-F 2025' (FY ended Mar 2025) from SEC or Sony IR"
download ja "sony_ifrs_2024_ja.pdf" \
  "https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/S100W19Q.pdf"

# SoftBank Group
manual_note ja "softbank_ifrs_2024_en.pdf" \
  "https://group.softbank/en/ir/financials/annual_reports" \
  "Download 'Annual Report' (EN) — verify it has full FS with notes"
manual_note ja "softbank_ifrs_2024_ja.pdf" \
  "https://group.softbank/ir/financials/annual_reports" \
  "Download '有価証券報告書 2024' (JA)"

# Hitachi
manual_note ja "hitachi_ifrs_2024_en.pdf" \
  "https://www.hitachi.com/IR/library/annual/index.html" \
  "Download 'Annual Securities Report' or 'Integrated Report' (EN)"
manual_note ja "hitachi_ifrs_2024_ja.pdf" \
  "https://www.hitachi.co.jp/IR/library/annual/index.html" \
  "Download '有価証券報告書 2024' (JA)"

# Takeda
manual_note ja "takeda_ifrs_2024_en.pdf" \
  "https://www.takeda.com/investors/reports/sec-filings/" \
  "Download '20-F 2025' (FY ended Mar 2025) from SEC"
manual_note ja "takeda_ifrs_2024_ja.pdf" \
  "https://www.takeda.com/jp/investors/reports/annual-reports/" \
  "Download '有価証券報告書 2024' (JA)"

echo ""

# ─────────────────────────────────────────────────────────────
# KOREAN (KO) — 8 companies × 2 languages = 16 PDFs
# ─────────────────────────────────────────────────────────────
echo "── KO (Korean) ──"

# KB Financial Group
manual_note ko "kb_financial_ifrs_2024_en.pdf" \
  "https://www.kbfg.com/eng/ir/reports.do" \
  "Download '20-F 2024' from SEC or 'Annual Report' (EN)"
manual_note ko "kb_financial_ifrs_2024_ko.pdf" \
  "https://dart.fss.or.kr" \
  "Search for 'KB금융지주' on DART → 감사보고서 2024 (KO)"

# Samsung Life Insurance
manual_note ko "samsung_life_ifrs_2024_en.pdf" \
  "https://www.samsunglife.com/company/eng/ir/irInfo.do" \
  "Download 'Annual Report 2024' (EN)"
manual_note ko "samsung_life_ifrs_2024_ko.pdf" \
  "https://dart.fss.or.kr" \
  "Search for '삼성생명' on DART → 감사보고서 2024 (KO)"

# POSCO Holdings
manual_note ko "posco_ifrs_2024_en.pdf" \
  "https://www.posco-inc.com/eng/ir/reports.do" \
  "Download 'Annual Report 2024' or 20-F (EN)"
manual_note ko "posco_ifrs_2024_ko.pdf" \
  "https://dart.fss.or.kr" \
  "Search for 'POSCO홀딩스' on DART → 감사보고서 2024 (KO)"

# SK Innovation
manual_note ko "sk_innovation_ifrs_2024_en.pdf" \
  "https://www.skinnovation.com/eng/ir" \
  "Download 'Annual Report 2024' (EN)"
manual_note ko "sk_innovation_ifrs_2024_ko.pdf" \
  "https://dart.fss.or.kr" \
  "Search for 'SK이노베이션' on DART → 감사보고서 2024 (KO)"

# Samsung Electronics
manual_note ko "samsung_electronics_ifrs_2024_en.pdf" \
  "https://www.samsung.com/global/ir/reports-disclosures/sec-filings/" \
  "Download '20-F 2024' from SEC or Annual Report (EN)"
manual_note ko "samsung_electronics_ifrs_2024_ko.pdf" \
  "https://dart.fss.or.kr" \
  "Search for '삼성전자' on DART → 감사보고서 2024 (KO)"

# SK Telecom
manual_note ko "sk_telecom_ifrs_2024_en.pdf" \
  "https://www.sktelecom.com/en/ir/financial.do" \
  "Download '20-F 2024' from SEC (EN)"
manual_note ko "sk_telecom_ifrs_2024_ko.pdf" \
  "https://dart.fss.or.kr" \
  "Search for 'SK텔레콤' on DART → 감사보고서 2024 (KO)"

# Hyundai Motor
manual_note ko "hyundai_motor_ifrs_2024_en.pdf" \
  "https://www.hyundai.com/worldwide/en/company/ir/annual-report" \
  "Download 'Annual Report 2024' (EN)"
manual_note ko "hyundai_motor_ifrs_2024_ko.pdf" \
  "https://dart.fss.or.kr" \
  "Search for '현대자동차' on DART → 감사보고서 2024 (KO)"

# Celltrion
manual_note ko "celltrion_ifrs_2024_en.pdf" \
  "https://www.celltrion.com/en/ir/financialData.do" \
  "Download 'Annual Report 2024' (EN)"
manual_note ko "celltrion_ifrs_2024_ko.pdf" \
  "https://dart.fss.or.kr" \
  "Search for '셀트리온' on DART → 감사보고서 2024 (KO)"

echo ""

# ─────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────
echo "=== Download Summary ==="
total=0
downloaded=0
manual=0
for lang_dir in "$SCRIPT_DIR"/{at,ch,de,fr,es,pt,it,cz,hu,pl,no,sv,ja,ko}; do
  if [[ -d "$lang_dir" ]]; then
    count=$(find "$lang_dir" -name "*.pdf" 2>/dev/null | wc -l)
    lang=$(basename "$lang_dir")
    echo "  ${lang}/: ${count} PDFs"
    downloaded=$((downloaded + count))
  fi
done
echo ""
echo "Total downloaded: ${downloaded}"
echo ""
echo "For MANUAL downloads, visit each IR page listed above."
echo "Most companies require navigating to Investor Relations → Annual Reports → download PDF."
echo ""
echo "After downloading, run the pipeline:"
echo "  DOC_TAG_ROOT=/tmp/doc_tag bash eval/process_corpus.sh <fixture_names>"
