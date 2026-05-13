---
name: quantum-computing
description: Quantum computing fundamentals, quantum gates, algorithms, circuit design, and practical implementation using Qiskit and Cirq. Covers superposition, entanglement, interference, and real-world quantum applications.
origin: Orythix
---

# Quantum Computing

A comprehensive guide to quantum computing concepts, circuit design, and practical implementation.

## When to Use

- Explaining quantum computing fundamentals and concepts
- Designing quantum circuits and algorithms
- Writing quantum code in Qiskit, Cirq, or PennyLane
- Analyzing quantum algorithm complexity and advantages
- Discussing quantum hardware, noise, and error correction
- Comparing classical vs. quantum approaches to problems

---

## Core Concepts

### 1. Qubits vs Classical Bits

Classical bits are either 0 or 1. Qubits exist in a **superposition** — a linear combination of both states simultaneously until measured.

```
|ψ⟩ = α|0⟩ + β|1⟩
where |α|² + |β|² = 1
```

- `|α|²` = probability of measuring 0
- `|β|²` = probability of measuring 1
- After measurement, the qubit collapses to a definite classical state

### 2. Superposition

A qubit can represent 0 and 1 simultaneously. An n-qubit system can represent 2ⁿ states simultaneously — exponential parallelism.

```python
# Qiskit: Put a qubit into superposition using Hadamard gate
from qiskit import QuantumCircuit

qc = QuantumCircuit(1, 1)
qc.h(0)          # Hadamard: |0⟩ → (|0⟩ + |1⟩) / √2
qc.measure(0, 0) # 50% chance of 0, 50% chance of 1
```

### 3. Entanglement

Two qubits are entangled when the state of one instantly determines the state of the other, regardless of distance.

```python
# Create a Bell state (maximally entangled pair)
qc = QuantumCircuit(2, 2)
qc.h(0)          # Superpose qubit 0
qc.cx(0, 1)      # CNOT: entangle qubit 1 with qubit 0
qc.measure([0, 1], [0, 1])
# Result: always 00 or always 11 — never 01 or 10
```

### 4. Interference

Quantum algorithms use constructive interference to amplify correct answers and destructive interference to cancel wrong ones.

---

## Quantum Gates (Single-Qubit)

| Gate | Symbol | Matrix | Effect |
|------|--------|--------|--------|
| Hadamard | H | 1/√2 [[1,1],[1,-1]] | Superposition |
| Pauli-X | X | [[0,1],[1,0]] | Bit flip (NOT) |
| Pauli-Y | Y | [[0,-i],[i,0]] | Bit + phase flip |
| Pauli-Z | Z | [[1,0],[0,-1]] | Phase flip |
| S gate | S | [[1,0],[0,i]] | 90° phase rotation |
| T gate | T | [[1,0],[0,e^{iπ/4}]] | 45° phase rotation |
| Rx(θ) | Rx | rotation around X-axis | Parameterized rotation |

## Quantum Gates (Two-Qubit)

| Gate | Symbol | Effect |
|------|--------|--------|
| CNOT | CX | Flip target if control is \|1⟩ |
| CZ | CZ | Phase flip target if both \|1⟩ |
| SWAP | SWAP | Exchange two qubit states |
| Toffoli | CCX | CNOT with two controls |

---

## Quantum Algorithms

### Deutsch-Jozsa Algorithm
**Problem**: Determine if a function f(x) is constant or balanced with one query.
**Classical**: Needs 2^(n-1) + 1 queries worst case.
**Quantum**: Always 1 query — exponential speedup.

```python
from qiskit import QuantumCircuit

def deutsch_jozsa(oracle: QuantumCircuit, n: int) -> QuantumCircuit:
    """n = number of input qubits; oracle implements f(x)."""
    qc = QuantumCircuit(n + 1, n)
    # Initialize output qubit to |1⟩
    qc.x(n)
    # Apply Hadamard to all qubits
    qc.h(range(n + 1))
    # Apply oracle
    qc = qc.compose(oracle)
    # Apply Hadamard to input qubits
    qc.h(range(n))
    # Measure input qubits — all 0s = constant, any 1 = balanced
    qc.measure(range(n), range(n))
    return qc
```

### Grover's Search Algorithm
**Problem**: Find a marked item in an unsorted database of N items.
**Classical**: O(N) average.
**Quantum**: O(√N) — quadratic speedup.

```python
from qiskit import QuantumCircuit
import numpy as np

def grovers(n_qubits: int, target: int) -> QuantumCircuit:
    """Search for `target` among 2^n_qubits items."""
    N = 2 ** n_qubits
    iterations = int(np.pi / 4 * np.sqrt(N))  # Optimal iterations

    qc = QuantumCircuit(n_qubits, n_qubits)
    # Superpose all states
    qc.h(range(n_qubits))

    for _ in range(iterations):
        # Oracle: flip phase of target state
        target_bits = format(target, f'0{n_qubits}b')
        for i, bit in enumerate(reversed(target_bits)):
            if bit == '0':
                qc.x(i)
        qc.h(n_qubits - 1)
        qc.mcx(list(range(n_qubits - 1)), n_qubits - 1)
        qc.h(n_qubits - 1)
        for i, bit in enumerate(reversed(target_bits)):
            if bit == '0':
                qc.x(i)

        # Diffuser (amplitude amplification)
        qc.h(range(n_qubits))
        qc.x(range(n_qubits))
        qc.h(n_qubits - 1)
        qc.mcx(list(range(n_qubits - 1)), n_qubits - 1)
        qc.h(n_qubits - 1)
        qc.x(range(n_qubits))
        qc.h(range(n_qubits))

    qc.measure(range(n_qubits), range(n_qubits))
    return qc
```

### Quantum Fourier Transform (QFT)
Foundation of Shor's algorithm and phase estimation.

```python
from qiskit import QuantumCircuit
import numpy as np

def qft(n: int) -> QuantumCircuit:
    """Quantum Fourier Transform on n qubits."""
    qc = QuantumCircuit(n)
    for j in range(n):
        qc.h(j)
        for k in range(j + 1, n):
            angle = np.pi / (2 ** (k - j))
            qc.cp(angle, k, j)  # Controlled phase
    # Swap qubits to correct bit ordering
    for i in range(n // 2):
        qc.swap(i, n - i - 1)
    return qc
```

### Shor's Factoring Algorithm
**Problem**: Factor a large integer N into primes.
**Classical**: Sub-exponential but slow for large N.
**Quantum**: Polynomial time — breaks RSA encryption at scale.

Key steps:
1. Choose random `a < N`
2. Compute GCD(a, N) — if > 1, factor found classically
3. Use QFT-based period finding to find r where `a^r mod N = 1`
4. Use r to compute factors: `GCD(a^(r/2) ± 1, N)`

---

## Running on Real Hardware (Qiskit)

```python
from qiskit import QuantumCircuit, transpile
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

# Connect to IBM Quantum
service = QiskitRuntimeService(channel="ibm_quantum", token="YOUR_TOKEN")
backend = service.least_busy(operational=True, simulator=False)

# Build your circuit
qc = QuantumCircuit(2, 2)
qc.h(0)
qc.cx(0, 1)
qc.measure_all()

# Transpile for the specific backend's native gates and topology
transpiled = transpile(qc, backend=backend, optimization_level=3)

# Run with SamplerV2
sampler = SamplerV2(backend)
job = sampler.run([transpiled], shots=1024)
result = job.result()
print(result[0].data.meas.get_counts())
```

## Simulation (No Hardware Needed)

```python
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

sim = AerSimulator()

qc = QuantumCircuit(3, 3)
qc.h(0)
qc.cx(0, 1)
qc.cx(0, 2)  # 3-qubit GHZ state
qc.measure_all()

transpiled = transpile(qc, sim)
result = sim.run(transpiled, shots=1024).result()
counts = result.get_counts()
print(counts)  # Should show only '000' and '111'
```

---

## Google Cirq Patterns

```python
import cirq

# Create qubits
q0, q1 = cirq.LineQubit.range(2)

# Build circuit
circuit = cirq.Circuit([
    cirq.H(q0),
    cirq.CNOT(q0, q1),
    cirq.measure(q0, q1, key='result')
])
print(circuit)

# Simulate
simulator = cirq.Simulator()
result = simulator.run(circuit, repetitions=1000)
print(result.histogram(key='result'))
```

---

## PennyLane (Quantum ML)

```python
import pennylane as qml
import numpy as np

dev = qml.device("default.qubit", wires=2)

@qml.qnode(dev)
def variational_circuit(params):
    qml.RX(params[0], wires=0)
    qml.RY(params[1], wires=1)
    qml.CNOT(wires=[0, 1])
    return qml.expval(qml.PauliZ(0))

# Optimize using gradient descent
params = np.array([0.1, 0.2], requires_grad=True)
opt = qml.GradientDescentOptimizer(stepsize=0.1)
for step in range(100):
    params, cost = opt.step_and_cost(variational_circuit, params)
    if step % 20 == 0:
        print(f"Step {step}: cost = {cost:.4f}")
```

---

## Quantum Error Correction

Real quantum hardware is noisy. Error correction encodes logical qubits into many physical qubits.

```python
# 3-qubit bit-flip code (protects against X errors)
from qiskit import QuantumCircuit

def bit_flip_encode() -> QuantumCircuit:
    qc = QuantumCircuit(3)
    # Encode logical |0⟩ = |000⟩, logical |1⟩ = |111⟩
    qc.cx(0, 1)
    qc.cx(0, 2)
    return qc

def bit_flip_correct() -> QuantumCircuit:
    qc = QuantumCircuit(3, 1)
    # Majority vote using ancilla measurement
    qc.cx(0, 1)
    qc.cx(0, 2)
    qc.ccx(1, 2, 0)  # Toffoli corrects qubit 0
    qc.measure(0, 0)
    return qc
```

Key codes:
- **3-qubit code**: Protects against single bit-flip errors
- **Shor code** (9 qubits): Protects against any single-qubit error
- **Surface code**: Most hardware-practical, ~1% error threshold

---

## Quantum Advantage Landscape

| Problem | Classical | Quantum | Advantage |
|---------|-----------|---------|-----------|
| Unstructured search | O(N) | O(√N) | Quadratic |
| Integer factoring | Sub-exp | Polynomial | Exponential |
| Simulation (chemistry) | Exp | Polynomial | Exponential |
| Linear systems (HHL) | O(N) | O(log N) | Exponential* |
| Optimization (QAOA) | NP-hard | Heuristic | Unclear |
| Machine learning | Varies | Varies | Case-dependent |

*With caveats on data loading (QRAM problem)

---

## NISQ Era Algorithms (Current Hardware)

Current devices are **Noisy Intermediate-Scale Quantum (NISQ)** — 50-1000 qubits, no error correction.

### QAOA (Quantum Approximate Optimization)
```python
from qiskit.circuit.library import QAOAAnsatz
from qiskit_algorithms import QAOA
from qiskit_algorithms.optimizers import COBYLA

# Max-cut on a graph
from qiskit_optimization.applications import Maxcut
import networkx as nx

G = nx.Graph()
G.add_edges_from([(0,1), (0,3), (1,2), (2,3)])
maxcut = Maxcut(G)
problem = maxcut.to_quadratic_program()

qaoa = QAOA(optimizer=COBYLA(), reps=2)
result = qaoa.compute_minimum_eigenvalue(problem.to_ising()[0])
print(maxcut.interpret(result))
```

### VQE (Variational Quantum Eigensolver)
Used for quantum chemistry — find ground state energy of molecules.

```python
from qiskit_nature.second_q.drivers import PySCFDriver
from qiskit_nature.second_q.algorithms import GroundStateEigensolver
from qiskit_algorithms import VQE

# H2 molecule ground state energy
driver = PySCFDriver(atom="H 0 0 0; H 0 0 0.735", basis="sto3g")
problem = driver.run()

vqe = VQE(...)
solver = GroundStateEigensolver(mapper, vqe)
result = solver.solve(problem)
print(f"Ground state energy: {result.total_energies[0]:.4f} Hartree")
```

---

## Key Terms Quick Reference

| Term | Definition |
|------|-----------|
| Qubit | Quantum bit — superposition of 0 and 1 |
| Gate | Unitary operation on qubits |
| Circuit | Sequence of gates applied to qubits |
| Entanglement | Correlated quantum states across qubits |
| Superposition | Linear combination of basis states |
| Interference | Amplitude combination — can amplify or cancel |
| Decoherence | Loss of quantum properties due to environment |
| Fidelity | Measure of how close a state is to ideal |
| NISQ | Noisy Intermediate-Scale Quantum (current era) |
| Oracle | Black-box quantum operation encoding a problem |
| Ansatz | Parameterized quantum circuit for variational algorithms |
| T1/T2 | Qubit relaxation / dephasing time constants |

---

## Recommended Libraries

| Library | Use Case | Install |
|---------|----------|---------|
| Qiskit | IBM hardware + simulation | `pip install qiskit qiskit-aer` |
| Cirq | Google hardware + research | `pip install cirq` |
| PennyLane | Quantum ML + autodiff | `pip install pennylane` |
| QuTiP | Open quantum systems | `pip install qutip` |
| Strawberry Fields | Photonic quantum computing | `pip install strawberryfields` |

---

## Anti-Patterns to Avoid

- **Measuring mid-circuit without reset** — destroys superposition, ruins entanglement
- **Expecting deterministic results** — quantum circuits are probabilistic; always use sufficient shots
- **Ignoring transpilation** — raw circuits may not match hardware topology; always `transpile()`
- **Deep circuits on NISQ** — gate count × error rate ≈ failure; keep circuits shallow
- **Assuming QFT = DFT** — QFT gives phases, not amplitudes; extracting amplitudes still costs exponential reads
- **Simulating >30 qubits classically** — state vector grows as 2ⁿ; use approximate simulators beyond ~20 qubits
