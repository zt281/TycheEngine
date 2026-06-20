// Stub CTP DLL for testing CtpLoader module loading.
// Implements the minimal CTP API entry points required for testing.

#ifdef _WIN32
#  define WIN32_LEAN_AND_MEAN
#  include <windows.h>
#  define EXPORT __declspec(dllexport)
#else
#  define EXPORT __attribute__((visibility("default")))
#endif

#include <cstring>
#include <iostream>

// Minimal stub classes for CTP API
class CThostFtdcMdApiStub {
public:
    static CThostFtdcMdApiStub* Create(const char* flowPath, bool, bool, bool) {
        (void)flowPath;
        return new CThostFtdcMdApiStub();
    }
};

class CThostFtdcTraderApiStub {
public:
    static CThostFtdcTraderApiStub* Create(const char* flowPath, bool) {
        (void)flowPath;
        return new CThostFtdcTraderApiStub();
    }
};

extern "C" {

// Market Data API creation function
EXPORT void* CreateFtdcMdApi(const char* pszFlowPath, bool bIsUsingUdp, bool bIsMulticast, bool bIsDetectPkg) {
    (void)bIsUsingUdp;
    (void)bIsMulticast;
    (void)bIsDetectPkg;
    std::cerr << "[StubCtpDll] CreateFtdcMdApi called with flowPath=" << (pszFlowPath ? pszFlowPath : "null") << std::endl;
    return CThostFtdcMdApiStub::Create(pszFlowPath, false, false, false);
}

// Trader API creation function
EXPORT void* CreateFtdcTraderApi(const char* pszFlowPath, bool bIsDetectPkg) {
    (void)bIsDetectPkg;
    std::cerr << "[StubCtpDll] CreateFtdcTraderApi called with flowPath=" << (pszFlowPath ? pszFlowPath : "null") << std::endl;
    return CThostFtdcTraderApiStub::Create(pszFlowPath, false);
}

} // extern "C"
