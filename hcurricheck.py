import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import io
import time

# --- 1. 앱 설정 ---
st.set_page_config(page_title="고등학교 교육과정 엑셀 점검 시스템", layout="wide")
st.title("📊 2027학년도 교육과정 자율 점검 (엑셀 직접 분석형)")
st.markdown("""
이미지 OCR의 오차를 없애기 위해 **엑셀 파일(.xlsx)**을 직접 분석합니다. 
데이터가 정확하게 입력되므로 AI의 점검 결과 신뢰도가 매우 높습니다.
""")

# --- 2. 시스템 인스트럭션 (지침 데이터 최적화) ---
SYSTEM_INSTRUCTION = """
당신은 대한민국 고등학교 교육과정 전문가입니다. 제공된 교육과정 배당표 데이터(텍스트/표)를 바탕으로 '자율 점검표'의 17가지 항목을 정밀 점검하세요.

[데이터 특징]
이미지가 아닌 엑셀에서 추출된 텍스트이므로 숫자는 정확합니다. 데이터의 구조를 파악하여 학기별, 과목별 학점을 합산하고 규칙 위반 여부를 판단하세요.

[17개 핵심 점검 항목]
1. 총 이수 학점 (192 이상: 교과 174 + 창체 18)
2. 필수 이수 학점 (84 이상)
3. 학기 단위 이수 완결성
4. 공통 과목 우선 편성 (선택 과목 이전 학기에 편성되었는가)
5. 위계성 준수 (Ⅰ->Ⅱ 순서 확인)
6. 학기당 학점 균형 (최대/최소 학기 간 격차 5 이내)
7. 초과 이수 학점의 적정성
8. 과목별 학점 범위 (공통 3~4, 한국사 3, 과탐실 1, 선택 3~5, 예체능/교양 2~4, 스포츠/생애 1~2)
9. 교과군별 필수 이수 학점 충족 여부
10. 2022 개정 교육과정 과목 명칭 사용 (표준 명칭 확인)
11. 국·수·영 총합 제한 (81학점 초과 금지)
12. 한국사 1, 2 편성 (각 3학점씩 정확히 편성)
13. 체육 편성 (10학점 이상 및 1~6학기 매 학기 편성)
14. 종교 과목 선택권 보장 (대체 과목 편성 여부)
15. 동일 학년 내 동일 과목 동일 학점 여부
16. 과목명 정확성 (띄어쓰기, 오탈자 정밀 체크)
17. 기록 형식 준수 (선택 과목 수 및 학점 표기 방식)

[응답 형식 - JSON]
{
    "학교명": "추출된 학교 이름",
    "점검결과": {
        "총학점_192": "O/X (수치 포함)", "필수이수_84": "O/X (수치 포함)", "학기단위완결": "O/X (내용)",
        "공통과목우선": "O/X (내용)", "위계성준수": "O/X (내용)", "학기균형5학점": "O/X (격차 수치)",
        "국수영총합_81": "O/X (현 학점)", "한국사_3": "O/X (내용)", "체육매학기": "O/X (누락여부)",
        "명칭정확성": "O/X (틀린 명칭)"
    },
    "개선사항": "종합 의견 및 수정 제언 전문"
}
"""

# --- 3. 엑셀 데이터 추출 함수 ---

def extract_excel_data(uploaded_file):
    """엑셀 파일에서 모든 시트의 데이터를 텍스트로 변환"""
    try:
        # 모든 시트를 읽어옴
        all_sheets = pd.read_excel(uploaded_file, sheet_name=None)
        combined_text = ""
        
        for sheet_name, df in all_sheets.items():
            combined_text += f"\n[시트명: {sheet_name}]\n"
            # 결측값 처리 및 텍스트 변환
            combined_text += df.to_csv(index=False) # CSV 형태가 AI가 구조를 파악하기 좋음
            
        return combined_text
    except Exception as e:
        return f"엑셀 읽기 오류: {e}"

# --- 4. 분석 실행 함수 ---

def analyze_curriculum_text(model, excel_text, filename):
    try:
        # AI에게 텍스트 데이터 전달
        response = model.generate_content(f"파일명: {filename}\n다음은 교육과정 엑셀 데이터입니다:\n{excel_text}")
        
        res_text = response.text
        if "```json" in res_text:
            res_text = res_text.split("```json")[1].split("```")[0]
        elif "```" in res_text:
            res_text = res_text.split("```")[1].split("```")[0]
            
        data = json.loads(res_text.strip())
        
        # 데이터 평탄화
        flat_data = {"파일명": filename, "학교명": data.get("학교명", "미확인")}
        for k, v in data.get("점검결과", {}).items():
            flat_data[k] = v
        flat_data["종합의견"] = data.get("개선사항", "")
        
        return flat_data
    except Exception as e:
        return {"파일명": filename, "오류": str(e)}

# --- 5. 메인 UI ---

api_key = st.sidebar.text_input("🔑 Gemini API Key 입력", type="password")

if api_key:
    genai.configure(api_key=api_key)
    # 2.5 Flash 혹은 1.5 Flash 사용 (텍스트 분석이므로 속도가 매우 빠름)
    model = genai.GenerativeModel(
        model_name='gemini-1.5-flash',
        system_instruction=SYSTEM_INSTRUCTION
    )

    uploaded_files = st.file_uploader(
        "📁 점검할 교육과정 엑셀 파일(.xlsx)을 업로드하세요", 
        type=['xlsx'], 
        accept_multiple_files=True
    )

    if uploaded_files:
        if st.button(f"🚀 {len(uploaded_files)}개 파일 정밀 분석 시작"):
            results = []
            progress_bar = st.progress(0)

            for i, file in enumerate(uploaded_files):
                with st.spinner(f"분석 중: {file.name}..."):
                    # 1. 엑셀 데이터 추출
                    excel_text = extract_excel_data(file)
                    # 2. AI 분석
                    res = analyze_curriculum_text(model, excel_text, file.name)
                    results.append(res)
                    
                    progress_bar.progress((i + 1) / len(uploaded_files))
                    time.sleep(12) # RPM 제한 준수

            if results:
                st.divider()
                df = pd.DataFrame(results)
                st.subheader("📊 엑셀 기반 점검 리포트")
                st.dataframe(df, use_container_width=True)

                # 엑셀 다운로드
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                
                st.download_button(
                    "📥 점검 결과 엑셀 다운로드", 
                    output.getvalue(), 
                    "교육과정_엑셀점검_결과.xlsx"
                )
else:
    st.info("사이드바에 API Key를 입력해 주세요.")
