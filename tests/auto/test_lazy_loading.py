import unittest
from ancpbids import load_dataset, DatasetOptions
from tests.base_test_case import DS005_DIR

class LazyLoadingTestCase(unittest.TestCase):
    def test_lazy_loading(self):
        ds = load_dataset(DS005_DIR)
        # dataset_description is loaded lazily on first access
        self.assertIsNone(ds.get('dataset_description'))
        self.assertEqual("1.0.0rc2", ds.dataset_description.BIDSVersion)

        participants = ds.get_file("participants.tsv")
        self.assertIsNotNone(participants)
        self.assertIsNone(participants.get('contents'))
        self.assertEqual(16, len(participants.contents))

if __name__ == '__main__':
    unittest.main()
