# GitHub Issues Rules - Examples-Driven Development

## **MANDATORY Requirements for Every GitHub Issue**

### **1. Clarity & Documentation**
- **Detailed description** for another LLM to understand completely
- **Clear strategy** with step-by-step approach
- **Examples reference**: Which example script validates this issue (e.g., `example_user.py` for UserRepository)

### **2. Examples-Driven Validation (PRIORITY 1)**
- **Primary completion criteria**: `./run_all.py` passes completely
- **Examples Integration**: Corresponding example script must work (e.g., `example_user.py` for Issue #6)
- **Living documentation**: Examples ARE the documentation - no separate docs needed

### **3. Testing Requirements (PRIORITY ORDER)**
- **PRIORITY 1**: `./run_all.py` passes (examples work = API works)
- **PRIORITY 2**: `poetry run python run_test.py` passes (unit tests pass)
- **Both required**: Examples AND unit tests must pass before merge

### **4. Development Flow**
- **Examples-Driven Development**: Examples fail → Write tests → Implement → Examples pass
- **TDD Support**: Write unit tests to support example functionality
- **Branch workflow**: `git checkout -b feature/issue-name`

### **5. Git Workflow (NON-NEGOTIABLE)**
- Create new git branch for each issue
- Examples-driven implementation
- `./run_all.py` must pass before commit
- `poetry run python run_test.py` must pass
- Git add, commit, push, create PR, merge
- Close issue immediately after merge
- Switch to main and pull latest

### **6. Code Quality Standards**
- **No legacy code** - clean, modern implementations only
- **Examples validation** - feature works in real-world usage
- **Repository-level operations** - pure fullon_orm patterns

## **Examples-First Completion Criteria**

### **Feature Complete When:**
1. ✅ **Examples pass**: Corresponding example script runs successfully
2. ✅ **Integration works**: `./run_all.py` completes without errors  
3. ✅ **Unit tests pass**: `run_test.py` passes 100%
4. ✅ **Quality checks**: Linting, formatting, type checking

### **Repository-Specific Examples**
- **Issue #6 (UserRepository)** → `examples/example_user.py`
- **Issue #7 (BotRepository)** → `examples/example_bot.py`
- **Issue #8 (ExchangeRepository)** → `examples/example_exchange.py`
- **Issue #9 (OrderRepository)** → `examples/example_order.py`
- **Issue #10 (TradeRepository)** → `examples/example_trade.py`
- **Issue #11 (SymbolRepository)** → `examples/example_symbol.py`

## **Examples ARE the Contract**

**Why Examples-Driven?**
- **Integration tests**: Examples test the complete API stack
- **Living documentation**: Always up-to-date, executable
- **User experience**: Shows how developers will actually use the API
- **Acceptance criteria**: When examples pass, feature is ready for production

**Remember**: `./run_all.py` passing = API works = Issue complete = Ready for production! 🚀
