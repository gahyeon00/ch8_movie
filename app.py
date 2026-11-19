import re  # 문자열에서 특정 패턴(날짜, 괄호 등)을 찾기 위해 가져옵니다.
import pandas as pd  # 표 데이터를 다루고 가공하기 위해 가져옵니다.
import requests  # 웹페이지 HTML을 요청해 가져오기 위해 가져옵니다.
import streamlit as st  # 웹 앱 화면과 버튼, 차트 등을 만들기 위해 가져옵니다.
from bs4 import BeautifulSoup  # HTML 태그를 탐색하고 수정하기 위해 가져옵니다.


# 대상 위키백과 문서 주소를 상수로 지정합니다.
WIKI_URL = "https://ko.wikipedia.org/wiki/대한민국의_영화_흥행_기록"


def fetch_html(url: str) -> str:
    """위키백과 문서의 HTML 문자열을 가져오며 네트워크 오류를 처리합니다."""
    # 수업 실습용임을 밝히는 User-Agent 헤더를 설정합니다.
    headers = {
        "User-Agent": "PythonClassPracticeBot/1.0 (1st-year non-CS student lab; educational use)"
    }
    try:
        # timeout을 설정해 서버 응답이 너무 길어지는 것을 방지합니다.
        response = requests.get(url, headers=headers, timeout=10)
        # HTTP 상태 코드가 4xx, 5xx이면 HTTPError를 발생시킵니다.
        response.raise_for_status()
        # 한글 깨짐을 막기 위해 인코딩을 지정합니다.
        response.encoding = response.apparent_encoding or "utf-8"
        return response.text
    except requests.Timeout as exc:
        # 요청 시간이 초과된 경우 안내 메시지를 담아 예외를 다시 올립니다.
        raise RuntimeError("요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.") from exc
    except requests.ConnectionError as exc:
        # 인터넷 연결이나 서버 접속 자체가 실패한 경우입니다.
        raise RuntimeError("네트워크 연결에 실패했습니다. 인터넷 연결을 확인해 주세요.") from exc
    except requests.HTTPError as exc:
        # 404, 403, 500 등 HTTP 응답 오류인 경우입니다.
        status_code = exc.response.status_code if exc.response is not None else "알 수 없음"
        raise RuntimeError(f"HTTP 오류가 발생했습니다. (상태 코드: {status_code})") from exc
    except requests.RequestException as exc:
        # 그 외 requests 관련 예외를 포괄적으로 처리합니다.
        raise RuntimeError(f"웹페이지를 불러오는 중 오류가 발생했습니다: {exc}") from exc


def find_target_table(html: str):
    """wikitable 중 첫 줄에 '관객수'와 '감독'이 모두 있는 첫 번째 표를 찾습니다."""
    soup = BeautifulSoup(html, "html.parser")
    # class 속성에 'wikitable'이 포함된 모든 table 태그를 찾습니다.
    tables = soup.find_all("table", class_="wikitable")

    for table in tables:
        first_tr = table.find("tr")
        if not first_tr:
            continue

        # 첫 줄의 제목 칸(th) 텍스트를 모두 모아 공백을 정리합니다.
        headers = [th.get_text(" ", strip=True) for th in first_tr.find_all("th")]
        header_joined = " ".join(headers)

        # '관객수'와 '감독'이 모두 포함되어 있으면 원하는 표로 간주합니다.
        if "관객수" in header_joined and "감독" in header_joined:
            # 표 내부의 각주 번호(sup 태그)를 모두 제거합니다.
            for sup in table.find_all("sup"):
                sup.decompose()
            return table

    # 조건에 맞는 표를 찾지 못한 경우 예외를 발생시킵니다.
    raise ValueError("첫 줄에 '관객수'와 '감독'이 모두 있는 wikitable을 찾지 못했습니다.")


def parse_table_to_df(table) -> pd.DataFrame:
    """HTML table 요소를 읽어 제목(th)과 데이터 행(td)으로 DataFrame을 만듭니다."""
    rows = table.find_all("tr")
    if not rows:
        raise ValueError("표에 행(tr) 데이터가 없습니다.")

    # 첫 줄(tr)에서 제목 칸(th) 목록을 추출합니다.
    columns = [th.get_text(" ", strip=True) for th in rows[0].find_all("th")]
    if not columns:
        raise ValueError("표의 첫 줄에서 제목 칸(th)을 읽을 수 없습니다.")

    records = []
    # 두 번째 줄부터 마지막 줄까지 영화 한 편씩 td 칸을 읽습니다.
    for tr in rows[1:]:
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        # 빈 행이나 열 개수가 맞지 않는 행은 건너뜁니다.
        if not cells:
            continue
        if len(cells) < len(columns):
            cells.extend([""] * (len(columns) - len(cells)))
        elif len(cells) > len(columns):
            cells = cells[: len(columns)]
        records.append(cells)

    if not records:
        raise ValueError("표에서 영화 데이터 행(td)을 읽지 못했습니다.")

    return pd.DataFrame(records, columns=columns)


def find_column_name(df: pd.DataFrame, keywords: list[str]) -> str | None:
    """열 이름 목록에서 키워드가 포함된 실제 열 이름을 찾습니다."""
    for col in df.columns:
        col_clean = str(col).replace(" ", "")
        for kw in keywords:
            if kw.replace(" ", "") in col_clean:
                return col
    return None


def clean_movie_data(df: pd.DataFrame) -> pd.DataFrame:
    """제목 정제, 관객수 숫자 변환, 개봉연도 및 개봉월 파생을 수행합니다."""
    cleaned = df.copy()

    title_col = find_column_name(cleaned, ["영화", "제목"])
    audience_col = find_column_name(cleaned, ["관객수", "관객"])
    date_col = find_column_name(cleaned, ["개봉일", "개봉"])

    # 1) 제목에서 《》 기호를 제거합니다.
    if title_col:
        cleaned[title_col] = (
            cleaned[title_col]
            .astype(str)
            .str.replace("《", "", regex=False)
            .str.replace("》", "", regex=False)
            .str.strip()
        )

    # 2) 관객수에서 쉼표나 문자 등을 제거하고 정수형 숫자로 변환합니다.
    if audience_col:
        cleaned[audience_col] = (
            cleaned[audience_col]
            .astype(str)
            .str.replace(r"[^0-9]", "", regex=True)
        )
        cleaned[audience_col] = pd.to_numeric(cleaned[audience_col], errors="coerce")
        # 관객수가 숫자로 변환되지 않은 행(합계 행 등)은 제외합니다.
        cleaned = cleaned.dropna(subset=[audience_col]).copy()
        cleaned[audience_col] = cleaned[audience_col].astype(int)

    # 3) 개봉일에서 '개봉연도'와 '개봉월'을 추출합니다.
    years = []
    months = []
    if date_col:
        for val in cleaned[date_col].astype(str):
            # '2014-07-30', '2014. 7. 30.', '2014년 7월 30일' 같은 형태에서 연/월을 찾습니다.
            match = re.search(r"(\d{4})\D+(\d{1,2})", val)
            if match:
                years.append(int(match.group(1)))
                months.append(int(match.group(2)))
            else:
                year_only = re.search(r"(\d{4})", val)
                years.append(int(year_only.group(1)) if year_only else None)
                months.append(None)
    else:
        years = [None] * len(cleaned)
        months = [None] * len(cleaned)

    cleaned["개봉연도"] = years
    cleaned["개봉월"] = months

    return cleaned.reset_index(drop=True)


def render_dashboard(df: pd.DataFrame) -> None:
    """지표 카드, 정제된 표, 상위 10편 차트, 연도별 편수 차트를 화면에 출력합니다."""
    title_col = find_column_name(df, ["영화", "제목"]) or df.columns[0]
    audience_col = find_column_name(df, ["관객수", "관객"])

    if not audience_col:
        st.error("관객수 열을 찾을 수 없어 지표와 차트를 그릴 수 없습니다.")
        return

    # 관객수 내림차순으로 정렬해 역대 1위와 상위 10편을 계산합니다.
    sorted_df = df.sort_values(by=audience_col, ascending=False).reset_index(drop=True)
    ten_million_count = int((sorted_df[audience_col] >= 10_000_000).sum())
    top_movie_title = str(sorted_df.loc[0, title_col])
    top_audience = int(sorted_df.loc[0, audience_col])

    st.subheader("핵심 지표")
    col1, col2, col3 = st.columns(3)
    col1.metric("천만 영화 수", f"{ten_million_count}편")
    col2.metric("역대 1위", top_movie_title)
    col3.metric("1위 관객수", f"{top_audience:,}명")

    st.subheader("정제된 영화 목록")
    # hide_index=True로 설정해 DataFrame 기본 인덱스가 화면에 보이지 않게 합니다.
    st.dataframe(sorted_df, hide_index=True, use_container_width=True)

    st.subheader("관객수 상위 10편 (가로 막대 차트)")
    top10_df = sorted_df.head(10).set_index(title_col)[[audience_col]]
    # Streamlit의 bar_chart에서 horizontal=True로 가로 막대 차트를 그립니다.
    st.bar_chart(top10_df, horizontal=True)

    st.subheader("개봉 연도별 영화 편수 (막대 차트)")
    year_counts = (
        df["개봉연도"]
        .dropna()
        .astype(int)
        .value_counts()
        .sort_index()
        .rename("영화 편수")
    )
    year_counts.index = year_counts.index.astype(str)
    st.bar_chart(year_counts)


def main() -> None:
    """Streamlit 앱의 전체 실행 흐름을 제어합니다."""
    st.set_page_config(page_title="천만 관객 한국 영화 분석", layout="wide")
    st.title("대한민국 천만 관객 영화 흥행 기록 분석")
    st.write("위키백과 '대한민국의 영화 흥행 기록' 문서에서 표 데이터를 가져와 분석합니다.")

    # 세션 상태에 수집 및 정제된 데이터를 보관해 화면 갱신 시 유지합니다.
    if "movie_df" not in st.session_state:
        st.session_state["movie_df"] = None

    # ① 버튼을 누르면 requests로 데이터를 가져와 처리합니다.
    if st.button("데이터 가져오기 및 분석", type="primary"):
        try:
            with st.spinner("위키백과에서 표 데이터를 가져오는 중입니다..."):
                html = fetch_html(WIKI_URL)
                target_table = find_target_table(html)
                raw_df = parse_table_to_df(target_table)
                cleaned_df = clean_movie_data(raw_df)
                st.session_state["movie_df"] = cleaned_df
        except (RuntimeError, ValueError) as exc:
            st.error(str(exc))
            st.session_state["movie_df"] = None

    # 데이터가 준비되었을 때 ④ 시각화 결과를 화면에 보여줍니다.
    if st.session_state["movie_df"] is not None:
        render_dashboard(st.session_state["movie_df"])


if __name__ == "__main__":
    main()