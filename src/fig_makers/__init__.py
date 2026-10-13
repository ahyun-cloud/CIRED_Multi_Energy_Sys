"""fig_makers - 결과 시각화 함수 모음."""

#: 그림 함수들이 노드 키로 쓰는 항목
_SITE_KEYS = ("pv_sites", "ess_sites", "chp_sites")


def int_sites(results: dict) -> dict:
    """노드 키를 정수로 통일한 results 사본을 돌려준다.

    extractor 가 넘기는 결과는 노드 키가 int 지만, 같은 결과를 summary.json 으로
    저장했다 다시 읽으면 JSON 객체 키 규칙상 str 이 된다. 그대로 그리면
    plot_network 는 `str(n + 1)` 에서 TypeError 로 죽고, plot_siting 은 막대가
    문자열 정렬되어 Bus24·Bus7·Bus8 순으로 나온다. 재풀이 없이 그림만 다시
    만드는 경로(make_*_fig(s).py)를 위해 입구에서 한 번 정규화한다.
    """
    out = dict(results)
    for key in _SITE_KEYS:
        sites = out.get(key)
        if isinstance(sites, dict):
            out[key] = {int(k): v for k, v in sites.items()}
    return out
