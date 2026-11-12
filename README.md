# 전력반도체 Process Architecture & 시장 인텔리전스 플랫폼

GaN, SiC, SJ MOSFET, UD SGT 소자 동향·논문·이론 한계선($R_{on,sp}$ vs $BV$)·선진사 재무 벤치마크를 **매주 자동으로 업데이트**하고 **URL 하나로 팀원들과 공유**할 수 있는 웹 플랫폼입니다.

## 5분 만에 무료 URL 발급 및 자동 업데이트 켜기 (GitHub Pages)

1. **GitHub 저장소 생성**: GitHub에서 새 저장소(예: `power-semi-intel`)를 만들고 이 폴더의 모든 파일(`.github/`, `data/`, `scripts/`, `index.html`, `requirements.txt`)을 업로드(Push)합니다.
2. **GitHub Pages 활성화**: 저장소 **Settings → Pages → Build and deployment → Source**를 `GitHub Actions`로 선택합니다.
3. **권한 확인**: **Settings → Actions → General → Workflow permissions**에서 `Read and write permissions`를 선택해 저장합니다.
4. **첫 실행 & URL 확인**: **Actions** 탭에서 `Weekly Power Semiconductor Intelligence Update` 워크플로우를 `Run workflow`로 한 번 실행하면 `https://<아이디>.github.io/power-semi-intel/` URL이 생성됩니다. 이후 매주 월요일 오전 8시(KST)마다 자동 실행됩니다.

## 폴더 구조

* `index.html` — 5개 탭으로 구성된 고도화 대시보드 프론트엔드 (`data/dashboard_data.json` 실시간 로드)
* `data/dashboard_data.json` — 주차별 뉴스, 논문, 공정 매트릭스, 신뢰성·패키징, 재무·WSTS 시계열 데이터
* `scripts/update_dashboard.py` — arXiv API 및 전력반도체 RSS 피드 주간 자동 수집 스크립트
* `.github/workflows/weekly_update.yml` — 매주 자동 수집 및 GitHub Pages 재배포 워크플로우
