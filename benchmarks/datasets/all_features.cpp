// all_features.cpp -- C++ sample with all supported features
#include <iostream>
#include <string>
#include <cmath>
#include <cstdlib>

using namespace std;

// Forward declarations
int factorial(int n);
double circleArea(double r);

// Enum
enum Color { RED, GREEN, BLUE };

// Class
class Point {
public:
    int x;
    int y;
};

// Functions
int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}

double circleArea(double r) {
    return M_PI * r * r;
}

int main(int argc, char* argv[]) {
    // Variables
    int a = 10;
    float b = 3.14f;
    double c = 2.718;
    char ch = 'A';
    bool flag = true;
    const int MAX = 100;

    // String
    string name = "Hello";
    int len = name.length();

    // Output
    cout << "a = " << a << endl;
    cout << "b = " << b << endl;
    cout << "name = " << name << endl;
    cout << "length = " << len << endl;

    // Input
    int user_input;
    cout << "Enter a number: " << endl;
    cin >> user_input;

    // Arithmetic
    int sum = a + 5;
    int diff = a - 3;
    int product = a * 2;
    int quotient = a / 3;
    int remainder = a % 3;

    // Compound assignment
    sum += 10;
    diff -= 2;
    product *= 3;

    // Prefix/postfix
    a++;
    ++a;
    a--;

    // Ternary
    int absVal = (a > 0) ? a : -a;

    // Cast
    int rounded = static_cast<int>(b);

    // If/else
    if (a > 20) {
        cout << "big" << endl;
    } else if (a > 10) {
        cout << "medium" << endl;
    } else {
        cout << "small" << endl;
    }

    // For loop
    for (int i = 0; i < 5; i++) {
        cout << i << endl;
    }

    // While loop
    int n = 10;
    while (n > 0) {
        n--;
    }

    // Do-while
    do {
        n++;
    } while (n < 5);

    // Switch
    int day = 3;
    switch (day) {
        case 1: cout << "Monday" << endl; break;
        case 2: cout << "Tuesday" << endl; break;
        case 3: cout << "Wednesday" << endl; break;
        default: cout << "Other" << endl; break;
    }

    // Break/continue
    for (int i = 0; i < 20; i++) {
        if (i % 2 == 0) continue;
        if (i > 9) break;
        cout << i << endl;
    }

    // Math
    double sq = sqrt(16.0);
    double pw = pow(2.0, 3.0);
    double ab = abs(-5);
    cout << "sqrt(16) = " << sq << endl;
    cout << "pow(2,3) = " << pw << endl;

    // Function calls
    int fact = factorial(5);
    double area = circleArea(3.0);
    cout << "5! = " << fact << endl;
    cout << "area = " << area << endl;

    // Dynamic memory
    int* arr = new int[5];
    for (int i = 0; i < 5; i++) {
        arr[i] = i * 10;
    }
    delete[] arr;

    // Null pointer
    int* ptr = nullptr;
    if (ptr == nullptr) {
        cout << "null pointer" << endl;
    }

    // String operations
    string greeting = "Hello World";
    if (greeting.length() > 5) {
        cout << "long greeting" << endl;
    }

    return 0;
}
