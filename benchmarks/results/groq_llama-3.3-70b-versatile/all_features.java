import java.util.Scanner;
import java.lang.Math;

public class Main {
    public static int factorial(int n) {
        if (n <= 1) return 1;
        return n * factorial(n - 1);
    }

    public static int max(int a, int b) {
        return a > b ? a : b;
    }

    public static float average(float a, float b) {
        return (a + b) / 2.0f;
    }

    public static void printArray(int[] arr) {
        for (int i = 0; i < arr.length; i++) {
            System.out.print(arr[i] + " ");
        }
        System.out.println();
    }

    public static void main(String[] args) {
        // Variables
        int x = 10;
        float pi = 3.14f;
        double e = 2.718;
        char ch = 'A';
        long big = 999999;
        short small_val = 5;

        // Compound assignments
        x += 5;
        x -= 2;
        x *= 3;
        x /= 4;
        System.out.println("x = " + x);

        // Prefix / postfix
        int a = 3;
        a++;
        ++a;
        a--;
        --a;

        // if / else if / else
        if (x > 100) {
            System.out.println("big");
        } else if (x > 10) {
            System.out.println("medium");
        } else {
            System.out.println("small");
        }

        // for loop
        int sum = 0;
        for (int i = 1; i <= 10; i++) {
            sum += i;
        }
        System.out.println("sum = " + sum);

        // while
        int count = 0;
        while (count < 5) {
            count++;
        }

        // do-while
        int n = 10;
        do {
            n -= 3;
        } while (n > 0);
        System.out.println("n = " + n);

        // break / continue
        for (int i = 0; i < 20; i++) {
            if (i % 2 == 0) continue;
            if (i > 9) break;
            System.out.println(i);
        }

        // Arrays
        int[] arr = {10, 20, 30, 40, 50};
        int[] fib = {1, 1, 2, 3, 5, 8};
        arr[0] = 99;
        printArray(arr);
        printArray(fib);

        // Switch
        int day = 3;
        switch (day) {
            case 1: System.out.println("Mon"); break;
            case 2: System.out.println("Tue"); break;
            case 3: System.out.println("Wed"); break;
            default: System.out.println("Other"); break;
        }

        // Function calls
        int result = factorial(5);
        System.out.println("5! = " + result);
        System.out.println("max = " + max(42, 17));

        // String functions
        String name = "Hello";
        int len = name.length();
        System.out.println("len = " + len);

        // Math functions
        double sq = Math.sqrt(16.0);
        System.out.println("sqrt(16) = " + sq);

        // Ternary
        int abs_x = x > 0 ? x : -x;
        System.out.println("abs = " + abs_x);

        // Scanner
        Scanner scanner = new Scanner(System.in);
        System.out.print("Enter a number: ");
        int user_input = scanner.nextInt();
        System.out.println("You entered: " + user_input);
    }
}