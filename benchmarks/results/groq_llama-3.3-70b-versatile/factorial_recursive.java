import java.util.Scanner;

public class FactorialRecursive {
    public static long fact(int n) {
        if (n <= 1) return 1;
        return n * fact(n-1);
    }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        for (int i = 0; i < n; i++) {
            int val = scanner.nextInt();
            System.out.println(val + "! = " + (int)fact(val));
        }
        scanner.close();
    }
}