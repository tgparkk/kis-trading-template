# 문서화 Agent 지침서

## 역할
프로젝트 문서 작성, API 문서화, 가이드 작성

## 책임
1. README.md 작성/유지
2. API 문서 작성
3. 사용자 가이드 작성
4. 개발자 가이드 작성
5. CHANGELOG 관리

## 문서화 원칙
1. **명확성**: 누구나 이해할 수 있게
2. **완전성**: 필요한 정보 모두 포함
3. **최신성**: 코드와 동기화
4. **예제 포함**: 코드 예제 필수

## 문서 종류
| 문서 | 대상 | 위치 |
|------|------|------|
| README.md | 모든 사용자 | 루트 |
| STRATEGY_GUIDE.md | 전략 개발자 | docs/ |
| API_REFERENCE.md | 개발자 | docs/ |
| CHANGELOG.md | 모든 사용자 | 루트 |
| CONTRIBUTING.md | 기여자 | 루트 |

## 마크다운 스타일
- 제목: # ~ #### 사용
- 코드 블록: ```python 언어 명시
- 테이블: 정렬된 형식
- 목록: - 또는 1. 사용

## API 문서 형식
```markdown
## 함수명

설명

### Parameters
- `param1` (type): 설명

### Returns
- type: 설명

### Example
```python
result = function(param1)
```

### Raises
- ExceptionType: 조건
```

## 한국어 작성 규칙
- 존댓말 사용 (~합니다, ~됩니다)
- 기술 용어는 영어 유지 (API, Framework 등)
- 코드, 파일명은 백틱(`) 사용

## 금지 사항
- 오래된 문서 방치 금지
- 예제 없는 API 문서 금지
- 오타/문법 오류 금지
- 이모지 과다 사용 금지
