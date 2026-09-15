CREATE TEMP VIEW dart_cls AS
SELECT n.id, n.published_at, ns.stock_code, n.title,
  (n.title LIKE '%[기재정정]%' OR n.title LIKE '%[정정]%') AS is_amend,
  CASE
    WHEN n.title ~ '매매거래정지|정리매매|상장폐지|관리종목|투자주의환기|투자유의안내' THEN 'D1_거래정지_상폐'
    WHEN n.title ~ '불성실공시'                                          THEN 'D2_불성실공시'
    WHEN n.title ~ '유상증자'                                            THEN 'D3_유상증자'
    WHEN n.title ~ '무상증자'                                            THEN 'D4_무상증자'
    WHEN n.title ~ '감자|자본감소|주식병합'                              THEN 'D5_감자_주식병합'
    WHEN n.title ~ '전환사채|신주인수권부사채|교환사채|전환청구권|전환가액|신주인수권행사가액|교환가액' THEN 'D6_CB_BW_EB'
    WHEN n.title ~ '합병|분할'                                           THEN 'D7_합병_분할'
    WHEN n.title ~ '최대주주변경'                                        THEN 'D8_최대주주변경'
    WHEN n.title ~ '자기주식|주식소각'                                   THEN 'D9_자사주_소각'
    WHEN n.title ~ '\(잠정\)실적|결산실적|매출액또는손익구조|영업실적'    THEN 'E1_실적잠정'
    WHEN n.title ~ '단일판매|공급계약|신규시설투자'                      THEN 'E2_계약_투자'
    WHEN n.title ~ '풍문또는보도에대한해명|조회공시|투자판단관련주요경영사항' THEN 'E3_조회공시_해명'
    WHEN n.title ~ '소송등의|경영권분쟁'                                 THEN 'E4_소송_분쟁'
    WHEN n.title ~ '대량보유상황보고서|임원ㆍ주요주주특정증권|최대주주등소유주식변동' THEN 'R1_지분변동보고'
    WHEN n.title ~ '사업보고서|반기보고서|분기보고서|감사보고서'          THEN 'R2_정기보고서'
    WHEN n.title ~ '주주총회|의결권대리행사|주주명부'                     THEN 'R3_주총_주주명부'
    WHEN n.title ~ '투자설명서|일괄신고|증권신고서|증권발행실적|효력발생안내|소액공모' THEN 'R4_증권신고_발행'
    WHEN n.title ~ '기업설명회|IR'                                       THEN 'R5_IR'
    WHEN n.title ~ '현금ㆍ현물배당|배당'                                  THEN 'R6_배당'
    WHEN n.title ~ '타법인주식|출자증권취득|영업양수|자산양수|채무보증|자금대여|자금차입|담보제공|금전대여|단기차입금' THEN 'R7_투자_보증_대차'
    WHEN n.title ~ '주식매수선택권'                                      THEN 'R8_스톡옵션'
    WHEN n.title ~ '대규모기업집단현황|지급수단별|기업지배구조보고서|지속가능경영|공정거래자율준수|자산유동화관련|동일인등출자계열회사|신탁계약|기타시장안내|본점소재지|대표이사|사외이사|독립이사' THEN 'R9_루틴_기타공시'
    ELSE 'Z9_미분류'
  END AS dtype
FROM news n LEFT JOIN news_stock ns ON ns.news_id = n.id
WHERE n.source='dart';
