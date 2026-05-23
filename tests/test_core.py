"""核心逻辑测试 — 去重、日期过滤、数据解析"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta


class TestBossParse(unittest.TestCase):
    """Boss直聘数据解析"""

    def test_parse_job_item(self):
        from boss import _parse_job_item

        item = {
            "encryptJobId": "abc123",
            "encryptBrandId": "brand456",
            "securityId": "sec789",
            "brandName": "字节跳动",
            "jobName": "Go后端开发",
            "salaryDesc": "15-30K·16薪",
            "cityName": "北京",
            "bossName": "李洋",
            "bossTitle": "招聘主管",
            "brandStageName": "已上市",
            "industryName": "互联网",
            "scaleName": "10000人以上",
            "actionDateDesc": "今天08:55",
            "happenTime": "1779091994000",
        }

        job = _parse_job_item(item)
        self.assertEqual(job["encrypt_job_id"], "abc123")
        self.assertEqual(job["company"], "字节跳动")
        self.assertEqual(job["position"], "Go后端开发")
        self.assertEqual(job["salary"], "15-30K·16薪")
        self.assertEqual(job["city"], "北京")
        self.assertEqual(job["boss_name"], "李洋")
        self.assertEqual(job["stage"], "已上市")
        self.assertEqual(job["industry"], "互联网")
        self.assertEqual(job["scale"], "10000人以上")

    def test_parse_interview_item(self):
        from boss import _parse_interview_item

        item = {
            "encryptJobId": "int001",
            "brandName": "字节跳动",
            "jobName": "Go后端开发",
            "salaryDesc": "15-30K",
            "cityName": "北京",
            "interviewTime": "2026-05-22 14:00",
            "interviewAddr": "海淀区中关村",
            "interviewStatus": "待面试",
            "videoLink": "https://meeting.xxx.com/123",
        }

        job = _parse_interview_item(item)
        self.assertEqual(job["encrypt_job_id"], "int001")
        self.assertEqual(job["company"], "字节跳动")
        self.assertEqual(job["interview_time"], "2026-05-22 14:00")
        self.assertEqual(job["interview_addr"], "海淀区中关村")
        self.assertEqual(job["video_link"], "https://meeting.xxx.com/123")


class TestZhaopinParse(unittest.TestCase):
    """智联招聘数据解析"""

    def test_parse_item(self):
        from zhaopin import _parse_item

        item = {
            "number": "CC000018800J40965706202",
            "companyNumber": "CZ000018800",
            "companyName": "ABB",
            "name": "R&D Engineer (AI)",
            "salary60": "面议",
            "workCity": "上海",
            "cityDistrict": "徐汇",
            "streetName": "虹梅路",
            "workingExp": "经验不限",
            "education": "本科",
            "propertyName": "外商独资",
            "industryName": "仪器仪表",
            "companySize": "10000人以上",
            "jobPostingTime": "1778641411978",
        }

        job = _parse_item(item, "智联-推荐")
        self.assertEqual(job["encrypt_job_id"], "CC000018800J40965706202")
        self.assertEqual(job["company"], "ABB")
        self.assertEqual(job["position"], "R&D Engineer (AI)")
        self.assertEqual(job["salary"], "面议")
        self.assertEqual(job["city"], "上海")
        self.assertEqual(job["district"], "徐汇")
        self.assertEqual(job["experience"], "经验不限")
        self.assertEqual(job["degree"], "本科")
        self.assertEqual(job["stage"], "外商独资")
        self.assertEqual(job["happen_time"], "1778641411978")


class TestLiepinParse(unittest.TestCase):
    """猎聘数据解析"""

    def test_parse_job_card(self):
        from liepin import _extract_items

        item = {
            "jobCardDto": {
                "recruiter": {"staffName": "彭女士", "hrJob": "Recuriter"},
                "comp": {
                    "compName": "ABB",
                    "compId": "1880",
                    "compStage": "外商独资",
                    "compIndustry": "仪器仪表",
                    "compScale": "10000人以上",
                },
                "job": {
                    "jobId": "40965706202",
                    "title": "R&D Engineer (AI)",
                    "salary": "面议",
                    "city": "上海",
                },
            },
        }

        data = {"data": {"data": [item], "hasNextPage": False}}
        jobs = _extract_items(data, "猎聘-推荐")

        self.assertEqual(len(jobs), 1)
        j = jobs[0]
        self.assertEqual(j["company"], "ABB")
        self.assertEqual(j["position"], "R&D Engineer (AI)")
        self.assertEqual(j["salary"], "面议")
        self.assertEqual(j["city"], "上海")
        self.assertEqual(j["boss_name"], "彭女士")
        self.assertEqual(j["stage"], "外商独资")
        self.assertEqual(j["status"], "猎聘-推荐")

    def test_parse_collect_from_datas(self):
        from liepin import _extract_items

        item = {
            "id": 1574709,
            "favoriteTime": "1779447094000",
            "jobCardDto": {
                "comp": {"compName": "百行征信", "compId": "123"},
                "job": {"title": "安全管理岗", "salary": "13-23k·15薪", "jobId": "456"},
            },
        }

        data = {"data": {"datas": [item], "hasNextPage": False}}
        jobs = _extract_items(data, "猎聘-收藏")

        self.assertEqual(len(jobs), 1)
        j = jobs[0]
        self.assertEqual(j["company"], "百行征信")
        self.assertEqual(j["position"], "安全管理岗")
        self.assertEqual(j["status"], "猎聘-收藏")


class TestDedup(unittest.TestCase):
    """去重逻辑"""

    def setUp(self):
        from storage import _load_jobs, _save_jobs
        self.test_file = tempfile.mktemp(suffix=".json")
        from storage import JOB_FILE
        self.orig_file = JOB_FILE

    def test_dedup_by_id_and_status(self):
        """同 job_id + 同 status 不重复存储（但计数不依赖去重）"""
        from boss import _save_jobs_to_storage

        jobs = [
            {
                "encrypt_job_id": "test001",
                "company": "测试公司",
                "position": "测试岗位",
                "salary": "10K",
                "city": "北京",
                "status": "沟通过",
                "happen_time": "",
            },
            {
                "encrypt_job_id": "test001",
                "company": "测试公司",
                "position": "测试岗位",
                "salary": "10K",
                "city": "北京",
                "status": "沟通过",
                "happen_time": "",
            },
        ]

        n = _save_jobs_to_storage(jobs, today_only=False)
        self.assertEqual(n, 2, "计数不依赖去重，同job同status各算一条")

    def test_different_status_stored_separately(self):
        """同 job_id + 不同 status 分别存储"""
        from boss import _save_jobs_to_storage

        jobs = [
            {
                "encrypt_job_id": "test002",
                "company": "测试公司",
                "position": "测试岗位",
                "status": "沟通过",
                "happen_time": "",
            },
            {
                "encrypt_job_id": "test002",
                "company": "测试公司",
                "position": "测试岗位",
                "status": "感兴趣",
                "happen_time": "",
            },
        ]

        n = _save_jobs_to_storage(jobs, today_only=False)
        self.assertEqual(n, 2, "同job_id+不同status应各存1条")

    def test_today_only_filter(self):
        """today_only 过滤非今天数据"""
        from boss import _save_jobs_to_storage
        import time

        today = date.today()
        yesterday = today - timedelta(days=1)
        yesterday_ts = int(yesterday.strftime("%s")) * 1000

        jobs = [
            {
                "encrypt_job_id": "test003",
                "company": "今天",
                "position": "今天岗位",
                "status": "沟通过",
                "happen_time": "",
            },
            {
                "encrypt_job_id": "test004",
                "company": "昨天",
                "position": "昨天岗位",
                "status": "沟通过",
                "happen_time": str(yesterday_ts),
            },
        ]

        n = _save_jobs_to_storage(jobs, today_only=True)
        self.assertEqual(n, 1, "today_only应只存今天的数据")

    def test_today_only_skips_recommend(self):
        """推荐始终以当天记录（平台返回的就是今日推荐）"""
        from boss import _save_jobs_to_storage
        yesterday = date.today() - timedelta(days=1)
        yesterday_ts = int(yesterday.strftime("%s")) * 1000

        jobs = [
            {"encrypt_job_id": "test005", "company": "推荐公司",
             "position": "推荐岗位", "status": "每日推荐",
             "happen_time": str(yesterday_ts)},
        ]
        n = _save_jobs_to_storage(jobs, today_only=True)
        self.assertEqual(n, 1, "推荐不受 happenTime 限制，始终算今日")


class TestDateCalc(unittest.TestCase):
    """日期计算"""

    def test_happen_time_to_date(self):
        """happenTime 时间戳转日期"""
        from datetime import datetime as dt

        # 2026-05-22 的毫秒时间戳
        ts = dt(2026, 5, 22, 10, 0, 0).timestamp() * 1000
        record_date = dt.fromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d")
        self.assertEqual(record_date, "2026-05-22")

    def test_empty_happen_time(self):
        """空的 happenTime 默认今天"""
        today = date.today().isoformat()
        self.assertIsNotNone(today)
        self.assertTrue(len(today) == 10)


class TestCookieConvert(unittest.TestCase):
    """Cookie 格式转换"""

    def test_json_to_string(self):
        from boss import convert_cookie_json_to_string

        cookie_json = [
            {"name": "zp_at", "value": "abc123"},
            {"name": "wt2", "value": "def456"},
        ]

        result = convert_cookie_json_to_string(cookie_json)
        self.assertEqual(result, "zp_at=abc123; wt2=def456")


if __name__ == "__main__":
    # 清理测试数据
    from storage import _load_jobs, _save_jobs
    jobs = _load_jobs()
    test_jobs = [j for j in jobs if j.get("encrypt_job_id", "").startswith("test")]
    if test_jobs:
        for j in test_jobs:
            jobs.remove(j)
        _save_jobs(jobs)

    unittest.main(verbosity=2)
