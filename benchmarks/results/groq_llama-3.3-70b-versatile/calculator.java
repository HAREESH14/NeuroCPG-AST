import java.util.Scanner;

public class Calculator {
    public static float add(float a, float b) { return a + b; }
    public static float sub(float a, float b) { return a - b; }
    public static float mul(float a, float b) { return a * b; }
    public static float divide(float a, float b) { return b != 0 ? a / b : 0; }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        float a = scanner.nextFloat();
        float b = scanner.nextFloat();
        int op = scanner.nextInt();

        float result;
        switch (op) {
            case 1: result = add(a, b);    break;
            case 2: result = sub(a, b);    break;
            case 3: result = mul(a, b);    break;
            case 4: result = divide(a, b); break;
            default: result = 0;           break;
        }

        System.out.println("Result: " + result);

        for (int i = 1; i <= 5; i++) {
            if (i == 3) continue;
            System.out.println("i = " + i);
        }
    }
}