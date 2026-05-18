class MockSP:
    def __getattr__(self, name):
        return None

sp = MockSP()
