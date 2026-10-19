from unittest.mock import Mock

from curl_cffi.requests.exceptions import RequestException

from marketplace_mcp.adapters.wildberries.images import ImageFinder, _first_guess, _outward, url_for


def test_image_path_and_observed_basket_guess() -> None:
    assert _first_guess(100) == 1
    assert _first_guess(200) == 2
    assert "vol1/part100/100000/images/c516x688/1.webp" in url_for(100000, 2)
    assert _outward(2)[:5] == [2, 3, 1, 4, 5]


def test_finder_remembers_the_successful_basket() -> None:
    session = Mock()
    session.head.side_effect = [Mock(status_code=404), Mock(status_code=200)]
    finder = ImageFinder(session)
    expected = url_for(100000, 2)
    assert finder.find(100000) == expected
    session.head.reset_mock()
    session.head.side_effect = None
    session.head.return_value = Mock(status_code=200)
    assert finder.find(100001) == url_for(100001, 2)
    session.head.assert_called_once()


def test_unreachable_candidates_and_delisted_product_return_none() -> None:
    session = Mock()
    session.head.side_effect = RequestException("network down")
    finder = ImageFinder(session, timeout=0.01)
    assert finder.find(100000) is None
    assert session.head.call_count > 1
